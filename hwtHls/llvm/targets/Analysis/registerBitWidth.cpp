#include "registerBitWidth.h"
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include "../genericFpgaInstrInfo.h"

using namespace llvm;
namespace hwtHls {

bool checkOrSetWidth(MachineRegisterInfo &MRI, MachineOperand &op,
		unsigned width) {
	if (op.isReg()) {
		Register dstReg = op.getReg();
		LLT dstT = MRI.getType(dstReg);
		if (dstT.isValid()) {
			return dstT.getSizeInBits() == width;
		} else {
			MRI.setType(dstReg, LLT::scalar(width));
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
								&& "All values must be of same type");
			} else if (MO.isReg()) {
				Register R = MO.getReg();
				LLT T = MRI.getType(R);
				if (T.isValid()) {
					assert(
							T.getSizeInBits() == bitWidth
									&& "All values must be of same type");
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
			} else if (MO.isReg()) {
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
							errs() << R << " bitWidth:" << T.getSizeInBits()
									<< " previous bitWidth:" << bitWidth
									<< "\n";
							errs() << MI << "\n";
							MF.print(errs());
							errs() << "\n";
							llvm_unreachable(
									"All values for register must be of same type");
						}
					} else {
						if (T.getSizeInBits() != 1) {
							errs() << R << " bitWidth:" << T.getSizeInBits()
									<< "\n";
							errs() << MI << "\n";
							MF.print(errs());
							errs() << "\n";
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
		if (addrDef->getOpcode() != GenericFpga::GENFPGA_ARG_GET) {
			errs() << MI << "address defined in:\n" << *addrDef;
			llvm_unreachable(
					"Address for GENFPGA_CLOAD should be provided from function argument only");
		}
		auto fnArgI = addrDef->getOperand(1).getImm();
		auto a = MF.getFunction().getArg(fnArgI);
		auto argT = a->getType()->getNonOpaquePointerElementType();
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
		for (unsigned i = 0; i < srcCnt; i++) {
			auto width = MI.getOperand(1 + srcCnt + i).getImm();
			if (!checkOrSetWidth(MRI, MI.getOperand(1 + i), width)) {
				MF.dump();
				errs() << MI << " i:" << i << "\n";
				llvm_unreachable(
						"GENFPGA_MERGE_VALUES operand specified and actual width differs");
			}
			totalWidth += width;
		}
		assert(checkOrSetWidth(MRI, MI.getOperand(0), totalWidth));
		return true;
	}
	case GenericFpga::GENFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		auto dstWidth = MI.getOperand(3).getImm();
		assert(checkOrSetWidth(MRI, MI.getOperand(0), dstWidth));
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
		if (!resolveTypes(*MI)) {
			worklist.pop_front();
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
