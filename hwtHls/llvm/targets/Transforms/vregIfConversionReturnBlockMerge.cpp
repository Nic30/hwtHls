#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

#include <llvm/ADT/STLExtras.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/Transforms/utils/machineDceWorklist.h>

using namespace llvm;

namespace hwtHls {

bool VRegIfConverter::returnBlockMerge(MachineFunction &MF) {
	bool Changed = false;
	MachineBasicBlock *returnBlock = nullptr;
	llvm::SetVector<MachineBasicBlock*> blocksForLivenessRecompute;
	MachineDceWorklist dce(*MRI, &Redefs);
	for (MachineBasicBlock &MBB : make_early_inc_range(MF)) {
		if (MBB.succ_empty() && !MBB.terminators().empty()
				&& MBB.terminators().begin() == MBB.begin()
				&& MBB.size() == 1) {
			assert(
					MBB.isReturnBlock()
							&& "Currently implemented only for this instr.");
			if (returnBlock) {
				for (MachineBasicBlock *PredMBB : SmallVector<MachineBasicBlock*>(
						MBB.pred_begin(), MBB.pred_end())) {
					bool wasPredecessorOfNewRetBB = returnBlock->isPredecessor(
							PredMBB);
					bool hadFallThroughToOld = canFallThroughTo(*PredMBB, MBB);
					PredMBB->ReplaceUsesOfBlockWith(&MBB, returnBlock);
					if (wasPredecessorOfNewRetBB) {
						for (auto &TI : make_early_inc_range(
								PredMBB->terminators())) {
							std::optional<Register> C;
							if (TI.isConditionalBranch()) {
								C = TI.getOperand(0).getReg();
							}
							TI.eraseFromParent();
							if (C.has_value()) {
								dce.insert(C.value());
							}
						}
						hadFallThroughToOld = true;
					}
					if (hadFallThroughToOld
							&& returnBlock != PredMBB->getNextNode()) {
						InsertUncondBranch(*PredMBB, *returnBlock, TII);
					}
				}
				MBB.clear();
				Changed = true;
			} else {
				returnBlock = &MBB;
			}
		}
	}
	Changed |= dce.runToCompletition();
	if (Changed) {
		VRegLiveins->recompute();
	}
	return Changed;
}

}
