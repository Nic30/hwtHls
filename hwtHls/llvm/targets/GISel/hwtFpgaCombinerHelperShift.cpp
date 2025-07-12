#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/CodeGen/GlobalISel/CSEInfo.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace llvm {

void HwtFpgaCombinerHelper::rewriteConstShift(llvm::MachineInstr &MI) {
	auto dst = MI.getOperand(0);
	auto src = MI.getOperand(1);
	auto shAmount = MI.getOperand(2).getCImm()->getValue().getZExtValue();
	size_t srcWidth = MI.getOperand(3).getImm();
	Builder.setInstrAndDebugLoc(MI);

	auto Opc = MI.getOpcode();
	if (shAmount == 0) {
		// just copy
		Builder.buildInstr(HwtFpga::HWTFPGA_MUX, { dst }, { src });
	} else if (src.isCImm()) {
		APInt Val = src.getCImm()->getValue();
		assert(Val.getBitWidth() == srcWidth);
		switch (Opc) {
		case HwtFpga::HWTFPGA_ASHR:
			Val = Val.ashr(shAmount);
			break;
		case HwtFpga::HWTFPGA_LSHR:
			Val = Val.lshr(shAmount);
			break;
		case HwtFpga::HWTFPGA_SHL:
			Val = Val.shl(shAmount);
			break;
		default:
			errs() << MI;
			llvm_unreachable("Unknown type of shift");
		}
		Builder.buildConstant(dst, Val);
	} else {
		auto &Ctx = Builder.getContext();
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> ConcatMembers;
		size_t extractedWidth = srcWidth - shAmount;
		auto PaddingTy = IntegerType::get(Ctx, srcWidth - extractedWidth);
		switch (Opc) {
		case HwtFpga::HWTFPGA_ASHR: {
			hwtHls::CImmOrRegOrUndefWithWidth extract =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src,
							srcWidth, shAmount, extractedWidth);
			ConcatMembers.push_back(extract);
			hwtHls::CImmOrReg extracted(extract.reg);
			if (extract.c) {
				extracted = hwtHls::CImmOrReg(extract.c);
			}
			Register msb = hwtHls::buildMsbGet(Builder, Observer, extracted,
					extractedWidth, { });
			for (size_t i = extractedWidth; i < srcWidth; i++) {
				ConcatMembers.push_back(
						hwtHls::CImmOrRegOrUndefWithWidth(1, msb));
			}

			break;
		}
		case HwtFpga::HWTFPGA_LSHR: {
			hwtHls::CImmOrRegOrUndefWithWidth extract =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src,
							srcWidth, shAmount, extractedWidth);
			ConcatMembers.push_back(extract);
			ConcatMembers.push_back(
					hwtHls::CImmOrRegOrUndefWithWidth(
							ConstantInt::get(PaddingTy, 0)));
			break;
		}
		case HwtFpga::HWTFPGA_SHL: {
			ConcatMembers.push_back(
					hwtHls::CImmOrRegOrUndefWithWidth(
							ConstantInt::get(PaddingTy, 0)));
			hwtHls::CImmOrRegOrUndefWithWidth extract =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src,
							srcWidth, 0, extractedWidth);
			ConcatMembers.push_back(extract);

			break;
		}
		default:
			errs() << MI;
			llvm_unreachable("Unknown type of shift");
		}
		hwtHls::buildHWTFPGA_MERGE_VALUES(Builder, &Observer, dst.getReg(),
				ConcatMembers);
	}
	MI.eraseFromParent();
}
void HwtFpgaCombinerHelper::rewriteConstFunnelShift(llvm::MachineInstr &MI) {
	auto DstReg = MI.getOperand(0).getReg();
	auto src0 = MI.getOperand(1);
	auto src1 = MI.getOperand(2);
	auto shAmount = MI.getOperand(3).getCImm()->getValue().getZExtValue();
	size_t srcWidth = MI.getOperand(4).getImm();
	auto Opc = MI.getOpcode();
	Builder.setInstrAndDebugLoc(MI);
	if (shAmount == 0) {
		// just copy
		Builder.buildInstr(HwtFpga::HWTFPGA_MUX, { DstReg }, { src0 });
	} else if (src0.isCImm() && src1.isCImm()) {
		APInt Val0 = src0.getCImm()->getValue();
		APInt Val1 = src1.getCImm()->getValue();
		assert(Val0.getBitWidth() == srcWidth);
		assert(Val1.getBitWidth() == srcWidth);
		APInt Val;
		switch (Opc) {
		case HwtFpga::HWTFPGA_FSHL:
			Val = Val0.concat(Val1).shl(shAmount).extractBits(srcWidth, srcWidth);
			break;
		case HwtFpga::HWTFPGA_FSHR:
			Val = Val1.concat(Val0).lshr(shAmount).extractBits(srcWidth, 0);
			break;
		default:
			errs() << MI;
			llvm_unreachable("Unknown type of shift");
		}
		//auto MIB = Builder.buildInstr(HwtFpga::G_CONSTANT);
		//Observer.changingInstr(*MIB.getInstr());
		//MIB.add(dst);
		//auto ValAsC = ConstantInt::get(IntegerType::get(Builder.getContext(), srcWidth), Val);
		//MIB.addCImm(dyn_cast<ConstantInt>(ValAsC));
		//Observer.changedInstr(*MIB.getInstr());
		Builder.buildConstant(DstReg, Val);
	} else {
		llvm::SmallVector<hwtHls::CImmOrRegOrUndefWithWidth> ConcatMembers;
		switch (Opc) {
		case HwtFpga::HWTFPGA_FSHL: {
			// top shAmount bits of src1 as new low bits
			hwtHls::CImmOrRegOrUndefWithWidth src1Top =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src1,
							srcWidth, srcWidth - shAmount - 1, shAmount);

			// lower bits of src0 as new high bits
			hwtHls::CImmOrRegOrUndefWithWidth src0Bottom =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src0,
							srcWidth, 0, srcWidth - shAmount);

			assert(src1Top.width + src0Bottom.width == srcWidth);
			ConcatMembers.push_back(src1Top);
			ConcatMembers.push_back(src0Bottom);
			break;
		}
		case HwtFpga::HWTFPGA_FSHR: {
			// top width - shAmount bits of src0 as new low bits
			hwtHls::CImmOrRegOrUndefWithWidth src0Top =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src0,
							srcWidth, shAmount, srcWidth - shAmount);
			// lower bits of src1 as new high bits
			hwtHls::CImmOrRegOrUndefWithWidth src1Bottom =
					hwtHls::buildHWTFPGA_EXTRACT(Builder, &Observer, src0,
							srcWidth, 0, shAmount);
			assert(src0Top.width + src1Bottom.width == srcWidth);
			ConcatMembers.push_back(src0Top);
			ConcatMembers.push_back(src1Bottom);
			break;
		}
		default:
			errs() << MI;
			llvm_unreachable("Unknown type of funnel shift");
		}

		hwtHls::buildHWTFPGA_MERGE_VALUES(Builder, &Observer, DstReg,
				ConcatMembers);

	}
	MI.eraseFromParent();

}

}
