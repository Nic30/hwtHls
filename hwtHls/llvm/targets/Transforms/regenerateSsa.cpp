#include <hwtHls/llvm/targets/Transforms/regenerateSsa.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/CodeGen/GlobalISel/GISelChangeObserver.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/MachineInstr.h>

using namespace llvm;

namespace hwtHls {

bool regenerateSsaInMachineFunctionBlocks(llvm::GISelChangeObserver *Observer,
										  llvm::MachineFunction &MF) {
	if (MF.getProperties().hasIsSSA())
		return false;
	auto &MRI = MF.getRegInfo();
	const auto *TRI = MF.getSubtarget().getRegisterInfo();
	bool changed = false;
	for (auto &MBB : MF) {
		changed |= regenerateSsaInBasicBlock(MRI, TRI, Observer, MBB);
	}
	return changed;
}

bool regenerateSsaInBasicBlock(llvm::MachineRegisterInfo &MRI,
							   const llvm::TargetRegisterInfo *TRI,
							   llvm::GISelChangeObserver *Observer,
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
				SetVector<MachineInstr*> instrToUpdate;
				instrToUpdate.insert(&MI);
								
				for (MachineInstr *MI2 = MI.getNextNode(); MI2; MI2 = MI2->getNextNode()) {
					bool toUpdate = false;
					for (MachineOperand &op : MI2->uses()) {
						if (op.isReg() && op.getReg() == r) {
							usesToUpdate.push_back(&op);
							toUpdate = true;
						}
					}
					if (toUpdate) {
						instrToUpdate.insert(MI2);
					}
					if (MI2->definesRegister(r, TRI)) {
						changed = true;
						// replace only if this MI def is not last in the block
						auto bbLocalR = MRI.cloneVirtualRegister(r);
						if (Observer) {
							for (auto &_MI: instrToUpdate) {
								Observer->changingInstr(*_MI);
							}
						}
						defMo.setReg(bbLocalR);
						for (auto *op : usesToUpdate) {
							op->setReg(bbLocalR);
						}
						if (usesToUpdate.empty()) {
							defMo.setIsDead();
						} else {
							usesToUpdate.back()->setIsKill();
						}
						if (Observer) {
							for (auto &_MI: instrToUpdate) {
								Observer->changedInstr(*_MI);
							}
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
