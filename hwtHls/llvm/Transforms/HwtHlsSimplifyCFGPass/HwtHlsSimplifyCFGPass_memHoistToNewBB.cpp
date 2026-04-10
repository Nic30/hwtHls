#include <hwtHls/llvm/Transforms/utils/cfgUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_memSinkToNewBB.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/CFG.h>


#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>

using namespace llvm;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_memHoistToNewBB(llvm::DomTreeUpdater &DTU,
										  llvm::BasicBlock &BB) {
	if (succ_size(&BB) <= 2)
		return false; // this is something which normal hoist can do

	SmallVector<std::pair<BasicBlock *, LoadInst *>> toHoist;
	llvm::SmallVector<llvm::BasicBlock *> unreachableBBs;
	LoadInst *ld0 = findInstrAtSuccessorsBegin<LoadInst>(BB, false, toHoist, &unreachableBBs);
	if (toHoist.size() <= 1)
		return false;

	BasicBlock *hoistBB;
	if (toHoist.size() + unreachableBBs.size() == succ_size(&BB)) {
		// it is not necessary to generate new common sink for some predecessors,
		// because all predecessors were matched thus we can use this block 
		hoistBB = &BB;
	} else {
		hoistBB = llvm::BasicBlock::Create(BB.getContext());
		BB.getParent()->insert(BB.getIterator(), hoistBB);
		// extracts operands of PHIs to new sink block
		// because the BB will now have this predecessor instead of all selected
		// predecessors from toSink
		auto BBTerm = BB.getTerminator();
		auto hoistBBTerm = BB.getTerminator()->clone();
		hoistBBTerm ->insertBefore(*hoistBB, hoistBB->end());
		
		SmallVector<DomTreeUpdater::UpdateT> dtUpdates;
		for (const auto &[suc, st] : toHoist) {
			BBTerm->replaceSuccessorWith(suc, hoistBB);
			dtUpdates.push_back({DominatorTree::Delete, &BB, suc});
			dtUpdates.push_back({DominatorTree::Insert, &BB, hoistBB});
			dtUpdates.push_back({DominatorTree::Insert, hoistBB, suc});
		}
		SetVector<BasicBlock*> sucs;
		for (auto* suc: successors(hoistBB)) {
			sucs.insert(suc);
		}
		for (auto suc: sucs) {
			if (any_of(toHoist, [suc](std::pair<BasicBlock*, LoadInst*> p) { return p.first == suc; })) {
				continue; // BB -> hoistBB -> suc possible, thus must be preserved
			}
			if (isa<UnreachableInst>(suc->getTerminator()))
				continue;
			
			// BB jumps to hoistBB only for block which were subject to hoisting. 
			// If the block is not not one of the block with the hoisted load it means that
			// BB never jumps to hoistBB thus hoistBB can not jump anywhere thus the jump from hoistBB is safe
			// replace with jump to unreachable.
			auto unreachableBB = BasicBlock::Create(BB.getContext(), "memHoistToNewBB.unreachable", BB.getParent()); 
			(void)new UnreachableInst(BB.getContext(), unreachableBB);
			hoistBBTerm->replaceSuccessorWith(suc, unreachableBB);
			dtUpdates.push_back({DominatorTree::Insert, hoistBB, unreachableBB});
		}
		
		DTU.applyUpdates(dtUpdates);
	}
	auto hoistBBTerm = hoistBB->getTerminator()->getIterator();
	for (const auto &[suc, ld] : toHoist) {
		// hoist everything before st to BB
		BB.splice(hoistBBTerm, suc, suc->begin(),
				  ld->getIterator());
	}
	ld0->moveBefore(hoistBBTerm);
	for (const auto &[suc, ld] : toHoist) {
		if (ld != ld0) {
			ld->replaceAllUsesWith(ld0);
			ld->eraseFromParent();
		}
	}

	return true;
}

} // namespace hwtHls
