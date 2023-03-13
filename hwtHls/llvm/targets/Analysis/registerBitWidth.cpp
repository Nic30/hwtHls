#include "registerBitWidth.h"
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include "../genericFpgaInstrInfo.h"
#include "../bitMathUtils.h"

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
					undefsToDuplicate->push_back( {
							op.getParent()->getOperandNo(&op), width });
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
/*
 * Analyze type of operands and resolve type of other operands if possible
 * :returns: true if resolution was successful and all operands have known type
 **/
bool resolveTypes(MachineInstr &MI) {
	unsigned Opc = MI.getOpcode();
	MachineFunction &MF = *(MI.getParent()->getParent());
	MachineRegisterInfo &MRI = MF.getRegInfo();

	switch (Opc) {
	case GenericFpga::GENFPGA_ARG_GET:
	case TargetOpcode::G_BR:
	case TargetOpcode::G_BRCOND:
	case GenericFpga::PseudoRET:
		// no resolving needed
		return true;
	case TargetOpcode::G_CONSTANT:
		MRI.setType(MI.getOperand(0).getReg(),
				LLT::scalar(MI.getOperand(1).getCImm()->getBitWidth()));
		return true;
	case TargetOpcode::G_GLOBAL_VALUE: {
		auto ptrT = MI.getOperand(1).getGlobal()->getType();
		auto t = ptrT->getNonOpaquePointerElementType();
		unsigned SizeInBits = log2ceil(t->getArrayNumElements());
		LLT Ty = LLT::pointer(ptrT->getAddressSpace(), SizeInBits);
		MRI.setType(MI.getOperand(0).getReg(), Ty);
		return true;
	}
	case TargetOpcode::G_ICMP:
		MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(1));
		return true;
	case TargetOpcode::G_ADD:
	case TargetOpcode::G_SUB:
	case TargetOpcode::G_MUL:
	case TargetOpcode::G_AND:
	case TargetOpcode::G_OR:
	case TargetOpcode::G_XOR:
	case TargetOpcode::G_PTR_ADD:
	case GenericFpga::GENFPGA_NOT: {
		// all operands of same type
		unsigned bitWidth = 0;
		for (MachineOperand &MO : MI.operands()) {
			if (MO.isCImm()) {
				bitWidth = MO.getCImm()->getBitWidth();
				break;
			} else if (MO.isReg()) {
				LLT T = MRI.getType(MO.getReg());
				if (T.isValid()) {
					bitWidth = T.getSizeInBits();
				}
			}
		}
		if (bitWidth == 0)
			return false;
		for (MachineOperand &MO : MI.operands()) {
			if (MO.isCImm()) {
				assert(
						MO.getCImm()->getBitWidth() == bitWidth
								&& "All operands of this operator must be of same type");
			} else if (MO.isReg()) {
				Register R = MO.getReg();
				LLT T = MRI.getType(R);
				if (T.isValid()) {
					assert(
							T.getSizeInBits() == bitWidth
									&& "All operands of this operator must be of same type");
				} else {
					MRI.setType(R, LLT::scalar(bitWidth));
				}
			}
		}
		return true;
	}
	case GenericFpga::GENFPGA_MUX: {
		// 0 and odd operators of same type
		// even operators of 1b
		unsigned bitWidth = 0;
		unsigned OpI = 0;
		for (MachineOperand &MO : MI.operands()) {
			bool isValueOp = OpI == 0 || OpI % 2 == 1;
			if (!isValueOp)
				continue;
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
			return false;
		OpI = 0;
		for (MachineOperand &MO : MI.operands()) {
			bool isValueOp = OpI == 0 || OpI % 2 == 1;
			if (MO.isCImm()) {
				if (isValueOp) {
					assert(
							MO.getCImm()->getBitWidth() == bitWidth
									&& "All values must be of same type");
				} else {
					llvm_unreachable(
							"GENFPGA_MUX should not have a constant as a condition operand");
				}
			} else if (MO.isReg()) {
				Register R = MO.getReg();
				LLT T = MRI.getType(R);
				if (T.isValid()) {
					if (isValueOp) {
						if (T.getSizeInBits() != bitWidth) {
							if (MRI.def_empty(R)) {
								Register NewReg = MRI.createVirtualRegister(
										&GenericFpga::AnyRegClsRegClass);
								MO.setReg(NewReg);
								if (!checkOrSetWidth(MRI, MO, bitWidth,
										nullptr)) {
									llvm_unreachable(
											"GENFPGA_MERGE_VALUES set of type for register for operand with undefined value failed");
								}
							} else {
								MF.print(errs());
								errs() << "\n";
								errs() << R << " bitWidth:" << T.getSizeInBits()
										<< " previous bitWidth:" << bitWidth
										<< "\n";
								errs() << MI << "\n";
								llvm_unreachable(
										"All values for register must be of same type");
							}
						}
					} else {
						if (T.getSizeInBits() != 1) {
							MF.print(errs());
							errs() << "\n";
							errs() << R << " bitWidth:" << T.getSizeInBits()
									<< "\n";
							errs() << MI << "\n";
							llvm_unreachable(
									"All conditions must be of i1 type");
						}
					}
				} else {
					if (isValueOp) {
						MRI.setType(R, LLT::scalar(bitWidth));
					} else {
						MRI.setType(R, LLT::scalar(1));
					}
				}
			}
			OpI++;
		}
		return true;
	}

	case GenericFpga::GENFPGA_CSTORE:
	case GenericFpga::GENFPGA_CLOAD: {
		// val/dst, addr, index, cond
		auto *addrDef = MRI.getVRegDef(MI.getOperand(1).getReg());
		auto addrDefOpc = addrDef->getOpcode();
		Type * argT;
		if (addrDefOpc == GenericFpga::GENFPGA_ARG_GET) {
			auto fnArgI = addrDef->getOperand(1).getImm();
			auto a = MF.getFunction().getArg(fnArgI);
			argT = a->getType()->getNonOpaquePointerElementType();
		} else if (addrDefOpc == GenericFpga::G_GLOBAL_VALUE) {
			argT = addrDef->getOperand(1).getGlobal()->getType()->getNonOpaquePointerElementType();
		} else {
			errs() << MI << "address defined in:\n" << *addrDef;
			llvm_unreachable(
					"Address for GENFPGA_CLOAD should be provided from function argument only");
		}

		unsigned bitWidth;
		if (argT->isArrayTy()) {
			bitWidth = argT->getArrayElementType()->getIntegerBitWidth();
		} else {
			bitWidth = argT->getIntegerBitWidth();
		}

		if (MI.getOperand(0).isReg())
			MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(bitWidth));

		auto &cond = MI.getOperand(3);
		if (cond.isReg()) {
			Register R = cond.getReg();
			LLT T = MRI.getType(R);
			if (T.isValid()) {
				assert(
						T.getSizeInBits() == 1
								&& "All conditions must be of i1 type");
			} else {
				MRI.setType(R, LLT::scalar(1));
			}
		}
		return true;
	}
	case GenericFpga::GENFPGA_MERGE_VALUES: {
		// $dst $src{N}, $width{N}
		unsigned srcCnt = (MI.getNumOperands() - 1) / 2;
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
						"GENFPGA_MERGE_VALUES operand specified and actual width differs");
			}
			totalWidth += width;
		}
		if (undefsToDuplicate.size()) {
			for (auto &v : undefsToDuplicate) {
				Register Reg = MRI.createVirtualRegister(
						&GenericFpga::AnyRegClsRegClass);
				auto &O = MI.getOperand(v.first);
				O.setReg(Reg);
				if (!checkOrSetWidth(MRI, O, v.second, nullptr)) {
					llvm_unreachable(
							"GENFPGA_MERGE_VALUES set of type for register for operand with undefined value failed");
				}

			}
		}
		assert(checkOrSetWidth(MRI, MI.getOperand(0), totalWidth, nullptr));
		return true;
	}
	case GenericFpga::GENFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		auto dstWidth = MI.getOperand(3).getImm();

		assert(checkOrSetWidth(MRI, MI.getOperand(0), dstWidth, nullptr));
		auto offset = MI.getOperand(2).getImm();
		auto &src = MI.getOperand(1);

		if (src.isReg()) {
			LLT srcT = MRI.getType(src.getReg());
			if (srcT.isValid()) {
				if (unsigned(offset + dstWidth) > srcT.getSizeInBits()) {
					MF.dump();
					errs() << MI;
					llvm_unreachable(
							"GENFPGA_EXTRACT with incorret operands, selecting more bits than is provided from src");
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
	default: {
		//const auto *TII = MF.getSubtarget().getInstrInfo();
		errs() << "Not implemented for this instruction: " << MI << "\n";
		llvm_unreachable("Not implemented for this instruction");
	}
	}
	return false;
}

char GenFpgaRegisterBitWidth::ID = 0;
GenFpgaRegisterBitWidth::GenFpgaRegisterBitWidth() :
		MachineFunctionPass(ID) {
}

void GenFpgaRegisterBitWidth::getAnalysisUsage(llvm::AnalysisUsage &AU) const {
	MachineFunctionPass::getAnalysisUsage(AU);
}

bool GenFpgaRegisterBitWidth::runOnMachineFunction(llvm::MachineFunction &MF) {
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
				errs() << MI << "\n";
				llvm_unreachable("There is a single instruction in worklist which can not be resolved");
			}
			worklist.push_back(MI);
			cycleDetectionCntr -= 1;
		} else {
			cycleDetectionCntr = worklist.size() + 2;
		}
		if (cycleDetectionCntr == 0) {
			llvm_unreachable("Can not resolve type for some registers");
		}
	}
	return false;

}

}
