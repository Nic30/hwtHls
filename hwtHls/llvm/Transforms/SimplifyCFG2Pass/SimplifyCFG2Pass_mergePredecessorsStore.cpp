#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_mergePredecessorsStore.h>

#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/IteratedDominanceFrontier.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/IR/CFG.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

static Instruction* getInstructionBeforeTerminator(BasicBlock &BB) {
	auto *T = BB.getTerminator();
	if (T == BB.begin().getNodePtr()) {
		return nullptr; // this block is just terminator
	}
	return T->getPrevNode();
}

static bool isMergableStore(StoreInst *si0, StoreInst *si1) {
	if (!si0->isSameOperationAs(si1)) {
		return false; // stores a different type or has different special state (atomicity, alignment etc.)
	}
	if (si0->getPointerOperand() != si1->getPointerOperand())
		return false; // stores to a different destination
	return true;
}
///
/// Create a PHI node in BB for the operands of S0 and S1
///
PHINode *getStoreValuePHIOperand(BasicBlock &BB, ArrayRef<StoreInst*> stores) {
  // Create a phi if the values mismatch.
  Value *Opd0 = stores[0]->getValueOperand();
  bool allSame = true;
  for (auto *S: stores) {
	  if (S == stores[0])
		  continue;
	  if (S->getValueOperand() != Opd0) {
		  allSame = false;
		  break;
	  }
  }
  if (allSame)
	  return nullptr;

  auto *NewPN = PHINode::Create(Opd0->getType(), 2, Opd0->getName() + ".sink", &BB.front());
  for (auto *S: stores) {
	  NewPN->applyMergedLocation(NewPN->getDebugLoc(), S->getDebugLoc());
	  NewPN->addIncoming(S->getValueOperand(), S->getParent());
  }
  return NewPN;
}
/*
 * Sink stores with same pointer operand
 * based on llvm::MergedLoadStoreMotion::sinkStoresAndGEPs
 * */
static void sinkStores(ArrayRef<StoreInst*> stores, BasicBlock &TargetBB) {
	StoreInst *S0 = stores[0];
	// Hoist the instruction.
	BasicBlock::iterator InsertPt = TargetBB.getFirstInsertionPt();
	// Intersect optional metadata.
	for (auto *S1 : stores) {
		if (S1 == S0)
			continue;
		S0->andIRFlags(S1);
	}
	S0->dropUnknownNonDebugMetadata();
	for (auto *S1 : stores) {
		if (S1 == S0)
			continue;

		S0->applyMergedLocation(S0->getDebugLoc(), S1->getDebugLoc());
		S0->mergeDIAssignID(S1);
	}
	// Create the new store to be inserted at the join point.
	StoreInst *SNew = cast<StoreInst>(S0->clone());
	SNew->insertBefore(&*InsertPt);
	// New PHI operand? Use it.
	if (PHINode *NewPN = getStoreValuePHIOperand(TargetBB, stores))
		SNew->setOperand(0, NewPN); // (if NewPN == nullptr the original remains)
	for (auto *S1 : stores) {
		S1->eraseFromParent();
	}
}

bool SimplifyCFG2Pass_mergePredecessorsStore(llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BB) {

	SmallVector<BasicBlock*> predecessorsWithCommonStore;

	auto PredEnd = pred_end(&BB);
	for (pred_iterator Pred0it = pred_begin(&BB); Pred0it != PredEnd;
			++Pred0it) {
		BasicBlock &Pred0 = **Pred0it;
		Instruction *_lastStore0 = getInstructionBeforeTerminator(Pred0);
		if (!_lastStore0)
			continue;
		StoreInst *lastStore = dyn_cast<StoreInst>(_lastStore0);
		if (!lastStore)
			continue; // first instruction before terminator is not store

		predecessorsWithCommonStore.push_back(&Pred0);
		pred_iterator Pred1it = Pred0it;
		Pred1it++;
		for (; Pred1it != PredEnd; ++Pred1it) {
			BasicBlock &Pred1 = **Pred1it;
			Instruction *_lastStore1 = getInstructionBeforeTerminator(Pred1);
			if (!_lastStore1)
				continue;
			StoreInst *lastStore1 = dyn_cast<StoreInst>(_lastStore1);
			if (!lastStore1)
				continue; // first instruction before terminator is not store

			if (!isMergableStore(lastStore, lastStore1)) {
				continue;
			}
			predecessorsWithCommonStore.push_back(&Pred1);
		}
		if (predecessorsWithCommonStore.size() > 1)
			break; // successfully found multiple predecessors with common store

		// no other predecessor ends with this type of store, probe next block
		predecessorsWithCommonStore.clear();
	}
	if (predecessorsWithCommonStore.size()) {
		// resolve number of common stores
		size_t commonStoreCnt = 0; // we know it is >= 1 but we use this value to recognize first search for stores
		BasicBlock *Pred0 = nullptr;
		std::vector<SmallVector<StoreInst*>> commonStores;
		commonStores.reserve(predecessorsWithCommonStore.size());
		for (BasicBlock *OtherPred : predecessorsWithCommonStore) {
			if (!Pred0) {
				Pred0 = OtherPred;
			} else {
				size_t _commonStoreCnt = 0;
				StoreInst *lastStore0 = dyn_cast<StoreInst>(
						getInstructionBeforeTerminator(*Pred0));
				assert(lastStore0);
				StoreInst *lastStore1 = dyn_cast<StoreInst>(
						getInstructionBeforeTerminator(*OtherPred));
				if (commonStoreCnt == 0) {
					commonStores.push_back({});
				}
				commonStores.push_back({});

				SmallVector<StoreInst*> * commonStores0 = &commonStores[0];
				SmallVector<StoreInst*> & commonStores1 = commonStores.back();

				for (;;) {
					_commonStoreCnt += 1;
					if (commonStoreCnt == 0) {
						commonStores0->push_back(lastStore0);
					}
					commonStores1.push_back(lastStore1);

					if (commonStoreCnt != 0
							&& commonStoreCnt == _commonStoreCnt)
						break; // we do not search further because this is number of common stores from other block
					// and we are searching for number of common stores for all blocks
					if (lastStore0 == Pred0->begin().getNodePtr()) {
						break;
					}
					if (lastStore1 == OtherPred->begin().getNodePtr()) {
						break;
					}
					lastStore0 = dyn_cast<StoreInst>(lastStore0->getPrevNode());
					if (!lastStore0)
						break;
					lastStore1 = dyn_cast<StoreInst>(lastStore1->getPrevNode());
					if (!lastStore1)
						break;
				}
				if (commonStoreCnt == 0)
					commonStoreCnt = _commonStoreCnt;
				else
					commonStoreCnt = std::min(commonStoreCnt, _commonStoreCnt);

			}
		}
		// (also handles the update of PHIs in BB)
		BasicBlock * SinkBB = SplitBlockPredecessors(&BB, predecessorsWithCommonStore, ".sink.split", &DTU);
		if (!SinkBB)
			return false;
		for (size_t storeGroupI = 0; storeGroupI != commonStoreCnt; ++storeGroupI) {
			SmallVector<StoreInst*> stores;
			for (auto & storeInBlock: commonStores) {
				assert(storeInBlock.size() > storeGroupI);
				stores.push_back(storeInBlock[storeGroupI]);
			}
			// split Pred0 block to create block with just stores
			// create PHI to select store value
			sinkStores(stores, *SinkBB);
		}

		return true;
	}

	return false;
}

}
