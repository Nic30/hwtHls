#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_memSinkToNewBB.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>

using namespace llvm;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_memSinkToNewBB(llvm::DomTreeUpdater &DTU,
										  llvm::BasicBlock &BB) {
	if (pred_size(&BB) <= 2)
		return false; // this is something which normal sink can do

	SmallVector<std::pair<BasicBlock *, StoreInst *>> toSink;

	StoreInst *st0 = nullptr;
	for (auto *pred : predecessors(&BB)) {
		if (pred->getUniqueSuccessor() != &BB)
			continue;

		for (auto &I : reverse(*pred)) {
			if (isa<PHINode>(&I))
				break;
			if (auto st = dyn_cast<StoreInst>(&I)) {
				if (st0) {
					if (!st->isSameOperationAs(st0)) {
						// different access type, ptr type, volatility etc.
						break;
					}
					if (st->getPointerAddressSpace() != st0->getPointerAddressSpace()) {
						// some local memory or store for a different IO
						break;
					}
				} else {
					st0 = st;
				}
				toSink.push_back({pred, st});
				break;
			}
			if (auto term = dyn_cast<BranchInst>(&I)) {
				// support only unconditional br to BB for now
				if (term->isConditional())
					break;
			} else if (!isSafeToHoistInstr(&I, SkipFlags::NONE, false)) {
				break; // something with side-effect or store not found
			} else if (auto CI = dyn_cast<CallInst>(&I)) {
				if (!CI->getCalledFunction()->hasFnAttribute(
						Attribute::AttrKind::Speculatable)) {
					break;
				}
			}
		}
	}
	if (toSink.size() <= 1)
		return false;

	BasicBlock *sinkBB;
	if (toSink.size() == pred_size(&BB)) {
		// it is not necessary to generate new common sink for some predecessors,
		// because all predecessors were matched thus we can use this block 
		sinkBB = &BB;
	} else {
		sinkBB = llvm::BasicBlock::Create(BB.getContext());
		BB.getParent()->insert(BB.getIterator(), sinkBB);
		// extracts operands of PHIs to new sink block
		// because the BB will now have this predecessor instead of all selected
		// predecessors from toSink

		auto sinkBr = BranchInst::Create(&BB, sinkBB); // sinkBB br BB
		for (auto &PHI : BB.phis()) {
			auto newPhi = PHINode::Create(PHI.getType(), toSink.size());
			newPhi->insertBefore(sinkBr->getIterator());
			for (const auto &[pred, st] : toSink) {
				auto V = PHI.getIncomingValueForBlock(pred);
				assert(newPhi->getType() == V->getType());
				newPhi->addIncoming(V, pred);
			}
			for (const auto &[pred, st] : toSink) {
				PHI.removeIncomingValue(pred);
			}
			PHI.addIncoming(newPhi, sinkBB);
		}
		SmallVector<DomTreeUpdater::UpdateT> dtUpdates;
		for (const auto &[pred, st] : toSink) {
			pred->getTerminator()->replaceSuccessorWith(&BB, sinkBB);
			dtUpdates.push_back({DominatorTree::Delete, pred, &BB});
			dtUpdates.push_back({DominatorTree::Insert, pred, sinkBB});
		}
		dtUpdates.push_back({DominatorTree::Insert, sinkBB, &BB});
		DTU.applyUpdates(dtUpdates);
	}
	auto storeValPhi =
		PHINode::Create(st0->getValueOperand()->getType(), toSink.size());
	storeValPhi->insertBefore(*sinkBB, sinkBB->getFirstInsertionPt());
	for (const auto &[pred, st] : toSink) {
		storeValPhi->addIncoming(st->getValueOperand(), pred);
		if (st == st0) {
			st0->moveAfter(storeValPhi);
			st0->setOperand(0, storeValPhi);
		} else {
			assert(storeValPhi->getType() == st->getValueOperand()->getType());
			st->eraseFromParent();
		}
	}

	return true;
}

} // namespace hwtHls
