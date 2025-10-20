#include <hwtHls/llvm/targets/Transforms/regenerateSsa.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/MachineInstr.h>

using namespace llvm;

namespace hwtHls {

bool regenerateSsaInMachineFunctionBlocks(llvm::MachineFunction &MF) {
	bool isSSA = MF.getProperties().hasProperty(
			MachineFunctionProperties::Property::IsSSA);
	if (isSSA)
		return false;
	auto &MRI = MF.getRegInfo();
	bool changed = false;
	for (auto &MBB : MF) {
		changed |= regenerateSsaInBasicBlock(MRI, MBB);
	}
	return changed;
}

bool regenerateSsaInBasicBlock(llvm::MachineRegisterInfo &MRI,
		llvm::MachineBasicBlock &MBB) {
	bool changed = false;
	for (auto &MI : MBB) {
		for (MachineOperand &defMo : MI.defs()) {
			assert(defMo.isReg());
			Register r = defMo.getReg();
			if (MRI.hasOneDef(r))
				continue;
			bool hasUseInThisBB = false;
			for (auto &userOp : MRI.use_operands(r)) {
				if (userOp.getParent()->getParent() == &MBB) {
					hasUseInThisBB = true;
					break;
				}
			}
			if (hasUseInThisBB) {
				SmallVector<MachineOperand*> usesToUpdate;
				for (MachineInstr *MI2 = MI.getNextNode(); MI2; MI2 = MI2->getNextNode()) {
					for (MachineOperand &op : MI2->uses()) {
						if (op.isReg() && op.getReg() == r) {
							usesToUpdate.push_back(&op);
						}
					}
					if (MI2->definesRegister(r)) {
						// replace only if this MI def is not last in the block
						auto bbLocalR = MRI.cloneVirtualRegister(r);
						defMo.setReg(bbLocalR);
						for (auto *op : usesToUpdate) {
							op->setReg(bbLocalR);
						}
						if (usesToUpdate.empty()) {
							defMo.setIsDead();
						} else {
							usesToUpdate.back()->setIsKill();
						}
						break;
					}
				}
			}
		}
	}
	return changed;
}

}
