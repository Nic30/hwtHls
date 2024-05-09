#include <hwtHls/llvm/targets/Analysis/registerBitWidth.h>

#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/IR/Constants.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaIoUtils.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>

using namespace llvm;
namespace hwtHls {

bool checkOrSetWidth(MachineRegisterInfo &MRI, MachineOperand &op,
		unsigned width,
		llvm::SmallVector<std::pair<unsigned, uint64_t>> *undefsToDuplicate) {
	if (op.isReg()) {
		Register Reg = op.getReg();
		LLT dstT = MRI.getType(Reg);
		if (dstT.isValid()) {
			if (dstT.getSizeInBits() == width) {
				return true;
			} else if (undefsToDuplicate != nullptr) {
				// this may be undef which is shared with others and received a different type
				// we may be able to duplicate G_IMPLICIT_DEF to avoid type collision
				// at this point there should not be any G_IMPLICIT_DEF
				if (MachineOperand *Def = MRI.getOneDef(Reg)) {
					assert(
							Def->getParent()->getOpcode()
									!= TargetOpcode::G_IMPLICIT_DEF
									&& "This instruction should already be removed");
				} else if (MRI.def_empty(Reg)) {
					if (!MRI.hasOneUse(Reg)) {
						undefsToDuplicate->push_back( {
								op.getParent()->getOperandNo(&op), width });
					}
					return true;
				}
			}
			return false;
		} else {
			MRI.setType(Reg, LLT::scalar(width));
			return true;
		}
	} else {
		unsigned opWidth = op.getCImm()->getType()->getIntegerBitWidth();
		return opWidth <= width;
	}
}

void checkOrSetWidth(MachineRegisterInfo &MRI, MachineOperand &MO,
		unsigned bitWidth) {
	if (MO.isCImm()) {
		auto *CI = MO.getCImm();
		auto w = MO.getCImm()->getBitWidth();
		if (w != bitWidth) {
			auto opc = MO.getParent()->getOpcode();
			if (MO.getParent()->getOperandNo(&MO) == 2
					&& (opc == HwtFpga::HWTFPGA_SHL
							|| opc == HwtFpga::HWTFPGA_ASHR
							|| opc == HwtFpga::HWTFPGA_LSHR)) {
				// shift amount can reuce bitwidth if we discover that the actual value
				// in register has fewer bits than during legalization
				assert(bitWidth < w);
				auto newVal = CI->getValue().trunc(bitWidth).getZExtValue();
				assert(
						newVal == CI->getValue().getZExtValue()
								&& "Value should not change during truncate of shiftamount operand");
				MO.setCImm(
						ConstantInt::get(
								IntegerType::get(CI->getContext(), bitWidth),
								newVal));
			} else {
				errs() << *MO.getParent() << "\n";
				errs() << MO << "  (width=" << w << ", expected=" << bitWidth
						<< ")\n";
				llvm_unreachable(
						"Operand value does not have expected bit width");
			}
		}
	} else if (MO.isReg()) {
		Register R = MO.getReg();
		LLT T = MRI.getType(R);
		if (T.isValid()) {
			if (T.getSizeInBits() != bitWidth) {
				if (MRI.def_empty(R)) {
					if (!MRI.hasOneUse(R)) {
						// this reg may have been used as undef constant on multiple places with different
						// bit width, we define new reg to prevent interference
						Register NewReg = MRI.createVirtualRegister(
								&HwtFpga::anyregclsRegClass);
						MO.setReg(NewReg);
						MO.setIsUndef();
					}
					if (!checkOrSetWidth(MRI, MO, bitWidth, nullptr)) {
						errs() << *MO.getParent() << "\n";
						errs() << MO << "\n";
						llvm_unreachable(
								"set of type for register for operand with undefined value failed");
					}
				} else {
					MO.getParent()->getParent()->print(errs());
					errs() << "\n";
					errs() << *MO.getParent() << "\n";
					errs() << MO << "  (width=" << T.getSizeInBits()
							<< ", expected=" << bitWidth << ")\n";
					llvm_unreachable(
							"Operand value does not have expected bit width");
				}
			}

		} else {
			MRI.setType(R, LLT::scalar(bitWidth));
		}
	}
}

void duplicateRegsForUndefValues(
		const llvm::SmallVector<std::pair<unsigned, uint64_t> > &undefsToDuplicate,
		MachineRegisterInfo &MRI, MachineInstr &MI) {
	for (auto &v : undefsToDuplicate) {
		Register Reg = MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);
		auto &O = MI.getOperand(v.first);
		O.setReg(Reg);
		O.setIsUndef();
		if (!checkOrSetWidth(MRI, O, v.second, nullptr)) {
			llvm_unreachable(
					"Set of type for register for operand with undefined value failed");
		}
	}
}


const MachineOperand & getMopReference(const MachineOperand* v) {
	return *v;
}

const MachineOperand & getMopReference(const MachineOperand & v) {
	return v;
}


inline unsigned tryResolveBitWidthFromOperand(MachineRegisterInfo &MRI, const MachineOperand & MO) {
	unsigned bitWidth = 0;
	if (MO.isCImm()) {
		bitWidth = MO.getCImm()->getBitWidth();
	} else if (MO.isReg()) {
		LLT T = MRI.getType(MO.getReg());
		if (T.isValid()) {
			bitWidth = T.getSizeInBits();
		}
	}
	return bitWidth;
}
template<typename Ty>
unsigned tryResolveBitWidthFromOperands(MachineRegisterInfo &MRI, Ty operands) {
	unsigned bitWidth = 0;
	for (auto _MO : operands) {
		const MachineOperand &MO = getMopReference(_MO);
		bitWidth = tryResolveBitWidthFromOperand(MRI, MO);
		if (bitWidth)
			break;
	}
	return bitWidth;
}

/*
 * Analyze type of operands and resolve type of other operands if possible
 * :returns: true if resolution was successful and all operands have known type
 **/
bool resolveTypes(MachineInstr &MI) {
	unsigned Opc = MI.getOpcode();
	MachineFunction &MF = *(MI.getParent()->getParent());
	MachineRegisterInfo &MRI = MF.getRegInfo();

	switch (Opc) {
	case HwtFpga::HWTFPGA_ARG_GET:
	case HwtFpga::HWTFPGA_BR:
	case HwtFpga::HWTFPGA_BRCOND:
	case HwtFpga::PseudoRET:
	case TargetOpcode::IMPLICIT_DEF:
		// no resolving needed
		return true;
		// constants should be already lowered to IMM or global values
		//case TargetOpcode::G_CONSTANT:
		//	MRI.setType(MI.getOperand(0).getReg(),
		//			LLT::scalar(MI.getOperand(1).getCImm()->getBitWidth()));
		//	return true;
	case HwtFpga::HWTFPGA_GLOBAL_VALUE: {
		auto ptrT = MI.getOperand(1).getGlobal()->getType();
		Type *_t;
		unsigned SizeInBits;
		std::tie(_t, SizeInBits) = getGlobalValueElementTypeAndAddressWidth(MI);
		LLT Ty = LLT::pointer(ptrT->getAddressSpace(), SizeInBits);
		MRI.setType(MI.getOperand(0).getReg(), Ty);
		return true;
	}
	case HwtFpga::HWTFPGA_ICMP:
		MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(1));
		return true;
	case HwtFpga::HWTFPGA_ADD:
	case HwtFpga::HWTFPGA_SUB:
	case HwtFpga::HWTFPGA_MUL:
	case HwtFpga::HWTFPGA_SDIV:
	case HwtFpga::HWTFPGA_UDIV:
	case HwtFpga::HWTFPGA_SREM:
	case HwtFpga::HWTFPGA_UREM:
	case HwtFpga::HWTFPGA_AND:
	case HwtFpga::HWTFPGA_OR:
	case HwtFpga::HWTFPGA_XOR:
	case HwtFpga::HWTFPGA_NOT: {
		// all operands of same type
		unsigned bitWidth = tryResolveBitWidthFromOperands(MRI, MI.operands());
		if (bitWidth == 0)
			return false;
		for (MachineOperand &MO : MI.operands()) {
			checkOrSetWidth(MRI, MO, bitWidth);
		}
		return true;
	}
	// shift, src, dst same, shiftAmount log2ceil(src.width()+1) bits
	case HwtFpga::HWTFPGA_LSHR:
	case HwtFpga::HWTFPGA_ASHR:
	case HwtFpga::HWTFPGA_SHL: {
		auto &dst = MI.getOperand(0);
		auto &src = MI.getOperand(1);
		auto &shiftAmount = MI.getOperand(2);
		std::vector dataOps( { &dst, &src });
		unsigned bitWidth = tryResolveBitWidthFromOperands(MRI, dataOps);
		if (bitWidth == 0)
			return false;
		for (auto MO : dataOps)
			checkOrSetWidth(MRI, *MO, bitWidth);
		unsigned shWidth = log2ceil(bitWidth + 1);
		checkOrSetWidth(MRI, shiftAmount, shWidth);
		return true;
	}
	// bit counts, dst of log2ceil(src.width()+1) width
	case HwtFpga::HWTFPGA_CTLZ_ZERO_UNDEF:
	case HwtFpga::HWTFPGA_CTTZ_ZERO_UNDEF:
	case HwtFpga::HWTFPGA_CTLZ:
	case HwtFpga::HWTFPGA_CTTZ:
	case HwtFpga::HWTFPGA_CTPOP: {
		auto &dst = MI.getOperand(0);
		auto &src = MI.getOperand(1);
		unsigned dataBitWidth = tryResolveBitWidthFromOperand(MRI, src);
		if (dataBitWidth == 0)
			return false;
		unsigned shWidth = log2ceil(dataBitWidth + 1);
		checkOrSetWidth(MRI, dst, shWidth);
		return true;
	}
	case HwtFpga::HWTFPGA_MUX: {
		// 0 and odd operators of same type
		// even operators of 1b
		unsigned bitWidth = 0;
		unsigned OpI = 0;
		for (MachineOperand &MO : MI.operands()) {
			bool isValueOp = OpI == 0 || OpI % 2 == 1; // dst or any src val
			if (!isValueOp) {
				OpI++;
				continue;
			}
			if (MO.isCImm()) {
				bitWidth = MO.getCImm()->getBitWidth();
				break;
			} else if (MO.isReg() && !MRI.def_empty(MO.getReg())) {
				// :note: registers without def may be shared undef value and such a register may have wrong type
				//  (because this register was shared on every place where undef was used)
				LLT T = MRI.getType(MO.getReg());
				if (T.isValid()) {
					bitWidth = T.getSizeInBits();
					break;
				}
			}
			OpI++;
		}
		if (bitWidth == 0)
			return false; // can not resolve value type yet
		OpI = 0;
		for (MachineOperand &MO : MI.operands()) {
			bool isValueOp = OpI == 0 || OpI % 2 == 1; // dst or any src val
			checkOrSetWidth(MRI, MO, isValueOp ? bitWidth : 1);
			OpI++;
		}
		return true;
	}

	case HwtFpga::HWTFPGA_CSTORE:
	case HwtFpga::HWTFPGA_CLOAD: {
		// val/dst, addr, index, cond
		Type *elemT;
		size_t indexWidth;
		std::tie(elemT, indexWidth) = getLoadOrStoreElementType(MRI, MI);

		unsigned bitWidth = elemT->getIntegerBitWidth();

		if (MI.getOperand(0).isReg())
			MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(bitWidth));

		auto &cond = MI.getOperand(3);
		checkOrSetWidth(MRI, cond, 1);

		return true;
	}
	case HwtFpga::HWTFPGA_MERGE_VALUES: {
		// $dst $src{N}, $width{N}
		unsigned srcCnt = (MI.getNumExplicitOperands() - 1) / 2;
		unsigned totalWidth = 0;
		llvm::SmallVector<std::pair<unsigned, uint64_t>> undefsToDuplicate;
		for (unsigned i = 0; i < srcCnt; i++) {
			auto width = MI.getOperand(1 + srcCnt + i).getImm();
			auto &O = MI.getOperand(1 + i);
			if (!checkOrSetWidth(MRI, O, width, &undefsToDuplicate)) {
				MF.dump();
				errs() << MI << " i:" << i << ", " << O << ", " << width
						<< "\n";
				llvm_unreachable(
						"HWTFPGA_MERGE_VALUES operand specified and actual width differs");
			}
			totalWidth += width;
		}
		duplicateRegsForUndefValues(undefsToDuplicate, MRI, MI);
		assert(checkOrSetWidth(MRI, MI.getOperand(0), totalWidth, nullptr));
		return true;
	}
	case HwtFpga::HWTFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		auto dstWidth = MI.getOperand(3).getImm();

		assert(checkOrSetWidth(MRI, MI.getOperand(0), dstWidth, nullptr));
		auto offset = MI.getOperand(2).getImm();
		auto &src = MI.getOperand(1);
		if (src.isUndef()) {
			MF.dump();
			MI.dump();
			llvm_unreachable(
					"HWTFPGA_EXTRACT with undef as src operands should already be reduced");
		}
		if (src.isReg()) {
			LLT srcT = MRI.getType(src.getReg());
			if (srcT.isValid()) {
				if (unsigned(offset + dstWidth) > srcT.getSizeInBits()) {
					MF.dump();
					errs() << MI;
					llvm_unreachable(
							"HWTFPGA_EXTRACT with incorret operands, selecting more bits than is provided from src");
				}
				return true;
			}
		} else {
			unsigned srcWidth = src.getCImm()->getType()->getIntegerBitWidth();
			assert(offset + dstWidth <= srcWidth);
			return true;
		}

		return false;
	}
	case HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER:
	case HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE:
	case HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT:
	case HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT: {
		// $dst, $objId, $dstWidt, $src[n], $srcWidth[n]
		auto dstWidth = MI.getOperand(2).getImm();
		assert(checkOrSetWidth(MRI, MI.getOperand(0), dstWidth, nullptr));

		unsigned srcCnt = (MI.getNumExplicitOperands() - 3) / 2;
		llvm::SmallVector<std::pair<unsigned, uint64_t>> undefsToDuplicate;
		for (unsigned i = 0; i < srcCnt; i++) {
			auto width = MI.getOperand(3 + srcCnt + i).getImm();
			auto &O = MI.getOperand(3 + i);
			if (!checkOrSetWidth(MRI, O, width, &undefsToDuplicate)) {
				MF.dump();
				errs() << MI << " i:" << i << ", " << O << ", " << width
						<< "\n";
				llvm_unreachable(
						"operand specified and actual width differs");
			}
		}
		duplicateRegsForUndefValues(undefsToDuplicate, MRI, MI);

		return true;
	}
	default: {
		//const auto *TII = MF.getSubtarget().getInstrInfo();
		errs() << "Not implemented for this instruction: " << MI << "\n";
		llvm_unreachable("Not implemented for this instruction (G_* instructions should already be selected)");
	}
	}
	return false;
}

char HwtFpgaRegisterBitWidth::ID = 0;
HwtFpgaRegisterBitWidth::HwtFpgaRegisterBitWidth() :
		MachineFunctionPass(ID) {
}

void HwtFpgaRegisterBitWidth::getAnalysisUsage(llvm::AnalysisUsage &AU) const {
	MachineFunctionPass::getAnalysisUsage(AU); // preserve all
}

bool HwtFpgaRegisterBitWidth::runOnMachineFunction(llvm::MachineFunction &MF) {
	std::list<MachineInstr*> worklist;
	for (auto &MBB : MF) {
		for (auto &MI : MBB) {
			if (!resolveTypes(MI)) {
				worklist.push_back(&MI);
			}
		}
	}

	size_t cycleDetectionCntr = worklist.size() + 2;
	while (!worklist.empty()) {
		MachineInstr *MI = worklist.front();
		worklist.pop_front();
		if (!resolveTypes(*MI)) {
			if (worklist.empty()) {
				errs() << MI << " " << *MI << "\n";
				llvm_unreachable(
						"There is a single instruction in worklist which can not be resolved");
			}
			worklist.push_back(MI);
			cycleDetectionCntr -= 1;
		} else {
			cycleDetectionCntr = worklist.size() + 2;
		}
		if (cycleDetectionCntr == 0) {
			MF.dump();
			llvm_unreachable("Can not resolve type for some registers");
		}
	}
	return false;

}

}
