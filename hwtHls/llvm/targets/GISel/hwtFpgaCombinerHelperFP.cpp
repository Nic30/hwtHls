#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <math.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelValueTracking.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>

namespace llvm {

void HwtFpgaCombinerHelper::copyOperandsForHFloatTmpAndPredicate(MachineInstrBuilder & MIB, size_t offset, MachineInstr & MI) {
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();
	// add HFloatTmpConfig params
	for (size_t i = offset; i < offset + hwtHls::HFloatTmpConfig::MEMBER_CNT + 1; i++) {
		copyOperand(MIB, MRI, MF, MI.getOperand(i));
	}
}

bool HwtFpgaCombinerHelper::matchFMulByPow2(llvm::MachineInstr &MI,
		MatchFMulByPow2MatchInfo &shValue) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_FP_FMUL);
	assert(MI.getNumImplicitOperands() == 0);
	shValue.clear();
	auto &op0 = MI.getOperand(1);
	if (op0.isCImm())
		return false; // first normalize const to RHS or do const propagation
	auto &op1 = MI.getOperand(2);
	if (op1.isCImm()) {
		shValue.fpCfg =
				hwtHls::HFloatTmpConfig::fromMachineInstrOperands(MI, 3);
		auto op1f = shValue.fpCfg.bitCastHFloatTmpAPIntToAPFloat(
				op1.getCImm()->getValue());
		double op1d = op1f.convertToDouble();
		if (op1d == 0.0) {
			// x * 0.0 = 0.0
			shValue.isZero = true;
			return true;
		} else if (op1d == 1.0) {
			// x * 1.0 = x
			shValue.sh = 0;
			return true;
		} else {
			double op1log2 = log2(op1d);
			bool isPow2 = ceil(op1log2) == floor(op1log2);
			if (isPow2) {
				shValue.sh = ceil(op1log2);
				return true;
			}
		}
	}

	return false;
}

void HwtFpgaCombinerHelper::rewriteFMulByPow2(llvm::MachineInstr &MI,
		MatchFMulByPow2MatchInfo shValue) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_FP_FMUL);
	assert(MI.getNumImplicitOperands() == 0);
	auto &opDst = MI.getOperand(0);
	auto &op0 = MI.getOperand(1);
	auto &op1 = MI.getOperand(2);

	if (shValue.isZero) {
		// x * 0.0 = 0.0
		buildHwtFpgaCopy(opDst, op1);
	} else if (shValue.sh == 0) {
		// x * 1.0 = x
		buildHwtFpgaCopy(opDst, op0);
	} else {
		MachineInstrBuilder MIB = Builder.buildInstr(
				shValue.sh > 0 ? HwtFpga::HWTFPGA_FP_SHL : HwtFpga::HWTFPGA_FP_SHR);
		MachineBasicBlock &MBB = *MI.getParent();
		MachineFunction &MF = *MBB.getParent();
		MachineRegisterInfo &MRI = MF.getRegInfo();

		Observer.changingInstr(*MIB.getInstr());
		copyOperand(MIB, MRI, MF, opDst);
		copyOperand(MIB, MRI, MF, op0);
		IntegerType *shTy = IntegerType::getInt32Ty(
				MF.getFunction().getContext());
		MIB.addCImm(ConstantInt::get(shTy, int(std::abs(shValue.sh))));
		copyOperandsForHFloatTmpAndPredicate(MIB, 3, MI);
		Observer.changedInstr(*MIB.getInstr());
	}
	MI.eraseFromParent();
}
//std::optional<ValueAndVReg> op
//if (op1.isReg() && op1.getReg() && MRI.hasOneDef(op1.getReg())) {
//	auto VRegVal = getAnyConstantVRegValWithLookThrough(op1.getReg(), MRI);
//}
// match x HWTFPGA_FP_FDIV (2.0 HWTFPGA_FP_FPOWI sh)
bool HwtFpgaCombinerHelper::matchFDivByPowi(llvm::MachineInstr &MI,
		MatchFDivByPowiMatchInfo &shValue) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_FP_FDIV);
	assert(MI.getNumImplicitOperands() == 0);
	shValue.clear();
	auto &divRhs = MI.getOperand(2);
	if (!divRhs.isReg())
		return false;
	auto *V1Def = MRI.getOneDef(divRhs.getReg());
	if (!V1Def || V1Def->getParent()->getOpcode() != HwtFpga::HWTFPGA_FP_FPOWI) {
		return false;
	}
	auto& miFPowi = * V1Def->getParent();
	shValue.fpCfg = hwtHls::HFloatTmpConfig::fromMachineInstrOperands(MI, 3);
	auto base = miFPowi.getOperand(1);
	if (!base.isCImm())
		return false;
	auto sh = miFPowi.getOperand(2);
	if (!sh.isReg())
		return false;
	auto baseFloat = shValue.fpCfg.bitCastHFloatTmpAPIntToAPFloat(
			base.getCImm()->getValue());
	double baseD = baseFloat.convertToDouble();
	if (baseD == 0.0) {
		// x / (0.0 ** sh) = x / 0.0
		shValue.isDiv0 = true;
		return true;
	} else if (baseD == 1.0) {
		// x / (1.0 ** sh) = x
		shValue.isDiv1 = 0;
		return true;
	} else if (baseD == 2.0) {
		// x / (2.0 ** sh)
		auto shKB = VT->getKnownBits(sh.getReg());
		shValue.shWidth = shKB.One.getBitWidth();
		auto shMsbKB = shKB.extractBits(1, shKB.getBitWidth() - 1);
		if (shMsbKB.isAllOnes()) {
			shValue.knownValueOfShMsb = true;
		} else if (shMsbKB.isZero()) {
			shValue.knownValueOfShMsb = false;
		}
		return true;
	}

	return false;
}

void HwtFpgaCombinerHelper::rewriteFDivByPowi(llvm::MachineInstr &MI, MatchFDivByPowiMatchInfo shValue) {
	const auto *V1Def = MRI.getOneDef(MI.getOperand(2).getReg());
	const auto& miFPowi = * V1Def->getParent();
	const auto& sh = miFPowi.getOperand(2);
	const auto& x = MI.getOperand(1);
	const auto& dst = MI.getOperand(0);
	Builder.setInstrAndDebugLoc(MI);
	if (shValue.isDiv0) {
		llvm_unreachable("NotImplemented");
	} else if (shValue.isDiv1) {
		// x / (2.0 ** sh) = x
		buildHwtFpgaCopy(dst, MI.getOperand(1));
	} else {
		// x / (2.0 ** sh)
		if (!shValue.knownValueOfShMsb.has_value()) {
			// shift left or right depending on sign at runtime
			llvm_unreachable("NotImplemented");
		} else if (shValue.knownValueOfShMsb.value()) {
			// sh always negative, invert it and use
			// x / (2.0 ** (-sh) = x << (0-sh)
			llvm_unreachable("NotImplemented");
		} else {
			// sh >= 0, slice of msb and convert
			// x / (2.0 ** sh) = x >> trunc(sh, sh.width-1)
			hwtHls::CImmOrRegOrUndefWithWidth shTrunc = hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, sh,
					shValue.shWidth.value(), 0, shValue.shWidth.value() - 1);
			auto MIB0 = Builder.buildInstr(HwtFpga::HWTFPGA_FP_SHR);
			Observer.changingInstr(*MIB0.getInstr());
			MIB0.addDef(dst.getReg());
			MIB0.add(x);
			shTrunc.addAsUse(Builder, MIB0);
			copyOperandsForHFloatTmpAndPredicate(MIB0, 3, MI);
			Observer.changedInstr(*MIB0.getInstr());
		}
	}
	MI.eraseFromParent();
}

enum TrigonometricFnType {
	TRIG_NORMAL,
	TRIG_ARCUS,
	TRIG_PI,
	TRIG_HYPERBOLIC,
};

inline TrigonometricFnType TrigonometricFnType_get(unsigned Opcode) {
	switch (Opcode) {
	case HwtFpga::HWTFPGA_FP_SIN:
	case HwtFpga::HWTFPGA_FP_COS:
		return TrigonometricFnType::TRIG_NORMAL;
	case HwtFpga::HWTFPGA_FP_SINPI:
	case HwtFpga::HWTFPGA_FP_COSPI:
		return TrigonometricFnType::TRIG_PI;
	case HwtFpga::HWTFPGA_FP_ASIN:
	case HwtFpga::HWTFPGA_FP_ACOS:
		return TrigonometricFnType::TRIG_ARCUS;
	case HwtFpga::HWTFPGA_FP_SINH:
	case HwtFpga::HWTFPGA_FP_COSH: {
		return TrigonometricFnType::TRIG_HYPERBOLIC;
	}
	default:
		llvm_unreachable("Unexpected opcode!");
	}
}

inline bool TrigonometricFnType_isAnyFormOfSin(unsigned Opcode) {
	switch (Opcode) {
	case HwtFpga::HWTFPGA_FP_SIN:
	case HwtFpga::HWTFPGA_FP_SINPI:
	case HwtFpga::HWTFPGA_FP_ASIN:
	case HwtFpga::HWTFPGA_FP_SINH:
		return true;
	case HwtFpga::HWTFPGA_FP_COS:
	case HwtFpga::HWTFPGA_FP_COSPI:
	case HwtFpga::HWTFPGA_FP_ACOS:
	case HwtFpga::HWTFPGA_FP_COSH:
		return false;
	default:
		llvm_unreachable("Unexpected opcode!");
	}
}

inline unsigned TrigonometricFnType_getComplementOpcode(unsigned Opcode) {
	switch (Opcode) {
	case HwtFpga::HWTFPGA_FP_SIN:
		return HwtFpga::HWTFPGA_FP_COS;
	case HwtFpga::HWTFPGA_FP_COS:
		return HwtFpga::HWTFPGA_FP_SIN;
	case HwtFpga::HWTFPGA_FP_SINPI:
		return HwtFpga::HWTFPGA_FP_COSPI;
	case HwtFpga::HWTFPGA_FP_COSPI:
		return HwtFpga::HWTFPGA_FP_COSPI;
	case HwtFpga::HWTFPGA_FP_ASIN:
		return HwtFpga::HWTFPGA_FP_ACOS;
	case HwtFpga::HWTFPGA_FP_ACOS:
		return HwtFpga::HWTFPGA_FP_ASIN;
	case HwtFpga::HWTFPGA_FP_SINH:
		return HwtFpga::HWTFPGA_FP_COSH;
	case HwtFpga::HWTFPGA_FP_COSH:
		return HwtFpga::HWTFPGA_FP_SINH;
	default:
		llvm_unreachable("Unexpected opcode!");
	}
}

/*
 * Based on bool llvm::CombinerHelper::matchCombineDivRem
 * */
bool HwtFpgaCombinerHelper::matchCombineSinCos(MachineInstr &MI,
		MachineInstr *&OtherMI) {
	unsigned Opcode = MI.getOpcode();
	Register Src1 = MI.getOperand(1).getReg();
	auto complementOpc = TrigonometricFnType_getComplementOpcode(Opcode);
	//if (!isLegalOrBeforeLegalizer( { SinCosOpcode, { MRI.getType(Src1) } }))
	//	return false;

	// Combine:
	//   %sin:_ = HWTFPGA_FP_SIN[PI] %src1:_, %src2:_
	//   %cos:_ = HWTFPGA_FP_COS[PI] %src1:_, %src2:_
	// into:
	//  %sin:_, %cos:_ = HWTFPGA_FP_SINCOS[PI] %src1:_, %src2:_

	for (auto &UseMI : MRI.use_nodbg_instructions(Src1)) {
		if (&UseMI == &MI)
			continue;
		if (MI.getParent() != UseMI.getParent()
				|| UseMI.getOpcode() != complementOpc)
			continue; // user not a target opcode or in different block

		if (!matchEqualDefs(MI, UseMI, 1))
			continue; // both writing to same dst, computation in parallel not possible
		if (!matchEqualDefs(MI, UseMI, MI.getNumExplicitOperands() - 1))
			continue; // enCond is not the same, we are not sure if to hoist and how to build merged enCond

		bool HFloatTmpConfigMatch = true;
		for (size_t i = 2; i < hwtHls::HFloatTmpConfig::MEMBER_CNT + 2; i++) {
			if (MI.getOperand(i).getImm() != UseMI.getOperand(i).getImm()) {
				HFloatTmpConfigMatch = false;
				break;
			}
		}
		if (!HFloatTmpConfigMatch)
			continue;

		assert(&MI != &UseMI);
		OtherMI = &UseMI;
		return true;
	}

	return false;
}

/*
 * Based on bool llvm::CombinerHelper::applyCombineDivRem
 * */
void HwtFpgaCombinerHelper::applyCombineSinCos(MachineInstr &MI,
		MachineInstr *&OtherMI) {
	unsigned Opcode = MI.getOpcode();
	assert(OtherMI && "OtherMI shouldn't be empty.");
	assert(&MI != OtherMI);

	Register DestSinReg, DestCosReg;
	if (TrigonometricFnType_isAnyFormOfSin(Opcode)) {
		DestSinReg = MI.getOperand(0).getReg();
		DestCosReg = OtherMI->getOperand(0).getReg();
	} else {
		DestSinReg = OtherMI->getOperand(0).getReg();
		DestCosReg = MI.getOperand(0).getReg();
	}

	// Check which instruction is first in the block so we don't break def-use
	// deps by "moving" the instruction incorrectly. Also keep track of which
	// instruction is first so we pick it's operands, avoiding use-before-def
	// bugs.
	MachineInstr *FirstInst;
	if (dominates(MI, *OtherMI)) {
		Builder.setInstrAndDebugLoc(MI);
		FirstInst = &MI;
	} else {
		Builder.setInstrAndDebugLoc(*OtherMI);
		FirstInst = OtherMI;
	}
	auto trigTy = TrigonometricFnType_get(Opcode);
	unsigned mergedInstrOpc;
	switch (trigTy) {
	default:
		llvm_unreachable("Unexpected opcode!");
	case TrigonometricFnType::TRIG_NORMAL:
		mergedInstrOpc = HwtFpga::HWTFPGA_FP_SINCOS;
		break;
	case TrigonometricFnType::TRIG_ARCUS:
		mergedInstrOpc = HwtFpga::HWTFPGA_FP_ASINCOS;
		break;
	case TrigonometricFnType::TRIG_PI:
		mergedInstrOpc = HwtFpga::HWTFPGA_FP_SINCOSPI;
		break;
	case TrigonometricFnType::TRIG_HYPERBOLIC:
		mergedInstrOpc = HwtFpga::HWTFPGA_FP_SINCOSH;
		break;
	}
	auto MIB = Builder.buildInstr(mergedInstrOpc); // , { DestSinReg, DestCosReg }, srcs
	Observer.changingInstr(*MIB.getInstr());
	MIB.addDef(DestSinReg);
	MIB.addDef(DestCosReg);
	// start at 1 to  copy also src, +2 because dst,src operands are before HFloatTmpConfig
	MIB.add(FirstInst->getOperand(1));
	copyOperandsForHFloatTmpAndPredicate(MIB, 2, MI); // 2 for dst, src in original MI

	Observer.changedInstr(*MIB.getInstr());

	MI.eraseFromParent();
	OtherMI->eraseFromParent();
}

}
