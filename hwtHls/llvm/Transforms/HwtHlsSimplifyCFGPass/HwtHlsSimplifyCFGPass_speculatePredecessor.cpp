#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_speculatePredecessor.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Constants.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

// #define HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_speculatePredecessor(llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BB) {
	if (&BB == &BB.getParent()->getEntryBlock())
		return false;
	auto sucBB = BB.getSingleSuccessor();
	if (!sucBB)
		return false;
	if (sucBB == &BB)
		return false;
	if (BB.getTerminator()->getMetadata(LLVMContext::MD_loop))
		return false;
	auto& DT = DTU.getDomTree();
	bool isLatchAndSucIsHeader = DT.dominates(sucBB, &BB);
	if (isLatchAndSucIsHeader)
		return false; // do not discard latches as it can lead to significant complication
	// of header phis which will then result into loop falling apart into potentially unfavorable nested loops during simplifyLoop

#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
	DTU.flush();
	assert(DTU.getDomTree().verify());
#endif

	// check that BB and sucBB do not have common predecessor or all phi values from it are the same
	SetVector<std::pair<PHINode*, PHINode*>> phisToMerge;
	SmallPtrSet<BasicBlock*, 32> commonPreds;
	bool isFirstCommonPred = true;

	for (auto *predBB : predecessors(&BB)) {
		for (auto *sucPred : predecessors(sucBB)) {
			if (predBB == sucPred) { // for common predecessors
				commonPreds.insert(predBB);
				for (auto &phi1 : sucBB->phis()) {
					auto fromBBVal = phi1.getIncomingValueForBlock(&BB);
					auto phi0 = dyn_cast<PHINode>(fromBBVal);
					if (phi0 && phi0->getParent() == &BB) {
						auto fromPredVal = phi1.getIncomingValueForBlock(
								predBB);
						auto fromPredVal0 = phi0->getIncomingValueForBlock(
								predBB);
						if (fromPredVal != fromPredVal0) {
							// can not merge becase phi in sucBB has BB phi as input that phi has a different value
							// for predBB, this means that phi0 BB is required to resolve the value for phi1
							return false;
						}
						if (isFirstCommonPred)
							phisToMerge.insert( { phi0, &phi1 });
					} else if (fromBBVal
							!= phi1.getIncomingValueForBlock(sucPred)) {
						// by inlining of the BB phi would not be ale to switch between different fales
						return false;
					}
				}
				isFirstCommonPred = false;
			}
		}
	}
	// mark BB phis used by sucBB phis to merge
	for (auto &phi1 : sucBB->phis()) {
		auto fromBBVal = phi1.getIncomingValueForBlock(&BB);
		auto phi0 = dyn_cast<PHINode>(fromBBVal);
		if (phi0 && phi0->getParent() == &BB) {
			phisToMerge.insert( { phi0, &phi1 });
		}
	}

	// check that block is cheap and may be speculated
	for (auto &I : BB) {
		if (I.mayHaveSideEffects() || I.isVolatile()) {
			return false;
		}
	}
	// check that successor phis are not using non phi instructions from BB
	for (auto &phi : sucBB->phis()) {
		for (Value *v : phi.incoming_values()) {
			if (auto vi = dyn_cast<Instruction>(v)) {
				if (!isa<PHINode>(vi) && vi->getParent() == &BB)
					return false;
			}
		}
	}
	// check that BB phis are used only by sucBB phi or not used by sucBB at all
	// (because if its used only by phi merge is possible)
	for (auto &phi : BB.phis()) {
		bool usedByPhi = false;
		bool usedByNonPhi = false;
		for (auto *U : phi.users()) {
			if (auto UI = dyn_cast<Instruction>(U)) {
				if (isa<PHINode>(UI) && UI->getParent() == sucBB) {
					if (usedByNonPhi)
						return false;
					usedByPhi = true;
				} else if (usedByPhi) {
					return false;
				} else {
					usedByNonPhi = true;
				}
			}
		}
	}
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
	errs() << "BB: " << BB.getName() << "\n";
	errs() << "commonPreds:\n";
	for (auto predBB: commonPreds)
		errs() << "    : " << predBB->getName() << "\n";
	errs() << "before: \n";
	BB.getParent()->dump();
	errs() << "\n";
#endif
	// sink non phi/terminal instructions from BB to sucBB
	sucBB->splice(sucBB->getFirstInsertionPt(), &BB,
			BB.getFirstNonPHI()->getIterator(),
			BB.getTerminator()->getIterator());

	// sink phis which are arguments of phi in sucBB
	SmallPtrSet<PHINode*, 32> resolvedPhisInBB;
	SmallPtrSet<PHINode*, 32> resolvedPhisInSucBB;
	for (const auto& [phi0, phi1] : phisToMerge) {
		resolvedPhisInBB.insert(phi0);
		resolvedPhisInSucBB.insert(phi1);
		for (size_t i = 0; i < phi0->getNumIncomingValues(); ++i) {
			auto bb = phi0->getIncomingBlock(i);
			auto v = phi0->getIncomingValue(i);
			if (commonPreds.contains(bb)) {
				assert(v == phi1->getIncomingValueForBlock(bb));
			} else {
				if (v == phi0)
					v = phi1;
				assert(!is_contained(phi1->blocks(), bb));
				phi1->addIncoming(v, bb);
			}
		}
	}

	SmallVector<DominatorTree::UpdateType> DTUpdates;
	DTUpdates.push_back( { DominatorTree::Delete, &BB, sucBB });
	SmallVector<BasicBlock*> succExtraPreds;
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
	errs() << "succExtraPreds: \n";
#endif
	for (auto *predBB : predecessors(&BB)) {
		DTUpdates.push_back( { DominatorTree::Delete, predBB, &BB });
		if (!is_contained(predecessors(sucBB), predBB)) {
			succExtraPreds.push_back(predBB);
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
			errs() << predBB->getName() << "\n";
#endif
			DTUpdates.push_back( { DominatorTree::Insert, predBB, sucBB });
			// for new predecessors of sucBB copy a value coming originally from BB if phi was not update yet
			// (new predecessors were always passing trough BB until now)
			for (auto &phi1 : sucBB->phis()) {
				if (!resolvedPhisInSucBB.contains(&phi1)) {
					auto v = phi1.getIncomingValueForBlock(&BB);
					assert(!is_contained(phi1.blocks(), predBB));
					phi1.addIncoming(v, predBB);
				}
			}

		}
	}
	for (auto &phi1 : sucBB->phis()) {
		phi1.removeIncomingValue(&BB);
	}
	// sink rest of the phis
	SmallVector<PHINode*> BBPhis;
	for (auto &phi : BB.phis()) {
		BBPhis.push_back(&phi);
	}
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
	errs() << "BBExtraPreds: \n";
#endif
	SmallVector<BasicBlock*> BBExtraPreds;
	for (auto *predOfSucBB : predecessors(sucBB)) {
		if (predOfSucBB != &BB
				&& !is_contained(predecessors(&BB), predOfSucBB)) {
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
			errs() << predOfSucBB->getName() << "\n";
#endif
			BBExtraPreds.push_back(predOfSucBB);
		}
	}
	for (PHINode *phi : reverse(BBPhis)) {
		if (resolvedPhisInBB.contains(phi)) {
			assert(phi->use_empty());
			phi->eraseFromParent();
		} else {
			phi->moveBefore(*sucBB, sucBB->begin());
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
			errs() << "moving: " << *phi << "\n";
#endif
			//phi->addIncoming(PoisonValue::get(phi->getType()), &BB); // add dummy value for DeleteDeadBlock
			if (BBExtraPreds.size()) {
				//auto v = PoisonValue::get(phi->getType());
				for (auto predBB : BBExtraPreds) {
					// parent phi value alive during iteration of child loop
					assert(!is_contained(phi->blocks(), predBB));
					phi->addIncoming(phi, predBB);
				}
			}
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
			errs() << "moved: " << *phi << "\n";
#endif
		}
	}
	SmallVector<BasicBlock*> preds(predecessors(&BB));
	for (auto *pred : preds) {
		pred->getTerminator()->replaceSuccessorWith(&BB, sucBB);
		simplifyBranchToSameDst(pred);
	}
	//DeleteDeadBlock(&BB, &DTU, true);
	// avoid delete of block to preserve parent iterator
	BB.getTerminator()->eraseFromParent();
	new UnreachableInst(BB.getContext(), &BB);
	sortPhiOperands(*sucBB);

	DTU.applyUpdates(DTUpdates);
	DTU.flush();
#ifdef HwtHlsSimplifyCFGPass_speculatePredecessor_TRACE
	assert(DTU.getDomTree().verify());
	errs() << "after: \n";
	BB.getParent()->dump();
	errs() << "\n";
#endif
	return true;
}

}
