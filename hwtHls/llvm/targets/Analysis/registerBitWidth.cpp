#include "registerBitWidth.h"
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include "../genericFpgaInstrInfo.h"

using namespace llvm;
namespace hwtHls {

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
		// no resolving needed
		return true;
	case TargetOpcode::G_CONSTANT:
		MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(MI.getOperand(1).getCImm()->getBitWidth()));
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
							errs() << R << " bitWidth:" << T.getSizeInBits() << " previous bitWidth:" << bitWidth << "\n";
							errs() << MI << "\n";
							MF.print(errs());
							errs() << "\n";
							llvm_unreachable("All values for register must be of same type");
						}
					} else {
						assert(
								T.getSizeInBits() == 1
										&& "All conditions must be of i1 type");
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
		// val/dst, addr, cond
		auto *addrDef = MRI.getVRegDef(MI.getOperand(1).getReg());
		assert(
				addrDef->getOpcode() == GenericFpga::GENFPGA_ARG_GET
						&& "Address for GENFPGA_CLOAD should be provided from function argument only");
		auto fnArgI = addrDef->getOperand(1).getImm();
		auto a = MF.getFunction().getArg(fnArgI);
		auto bitWidth =
				a->getType()->getNonOpaquePointerElementType()->getIntegerBitWidth();
		MRI.setType(MI.getOperand(0).getReg(), LLT::scalar(bitWidth));
		auto &cond = MI.getOperand(1);
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
	default: {
		const auto *TII = MF.getSubtarget().getInstrInfo();
		errs() << "Not implemented for this instruction: " << TII->getName(Opc)
				<< "\n";
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
