#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass/rerouteChildBackedgeAndTransferChildPhis.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/MemorySSAUpdater.h>

using namespace llvm;

namespace hwtHls {

static void updatePhiIncommingValuesInOldLatchBlock(
		llvm::BasicBlock *childLatch, BasicBlock *oldLatchBlock,
		BasicBlock *childHeader) {
	// if reusing old latch block we may not update
	// all phis because some of them may not be related
	// to phis in childHeader
	size_t predCnt = pred_size(oldLatchBlock);
	for (auto &oldLatchPhi : oldLatchBlock->phis()) {
		size_t valCnt = oldLatchPhi.getNumIncomingValues();
		if (valCnt != predCnt) {
			assert(predCnt == valCnt + 1);
			assert(oldLatchPhi.getBasicBlockIndex(childHeader) < 0);
			oldLatchPhi.addIncoming(PoisonValue::get(oldLatchPhi.getType()),
					childLatch);
		}
	}
}

static std::pair<PHINode*, bool> createPhiInHeaderForChild(PHINode &childPhi,
		const std::map<PHINode*, PHINode*> &associatedPhis,
		size_t headerPredCnt, Instruction *firstNonPhiOfHeader) {
	auto Ty = childPhi.getType();
	auto existingParentPhi = associatedPhis.find(&childPhi);
	bool reusingParentPhi = existingParentPhi != associatedPhis.end();
	PHINode *headerPhi;
	if (reusingParentPhi) {
		headerPhi = existingParentPhi->second;
		assert(childPhi.getType() == headerPhi->getType());
	} else {
		assert(!Ty->isPointerTy());
		headerPhi = PHINode::Create(Ty, headerPredCnt,
				childPhi.getName() + ".inChildHeader", firstNonPhiOfHeader->getIterator());
	}
	return {headerPhi, reusingParentPhi};
}

// create a phi in newLatchBlock which will switch between undef and value from the child loop body
static std::pair<PHINode*, bool> createPhiInNewLatch(
		const LoopFlattenUsingIfPass::Mode mode, llvm::Type *Ty,
		PHINode &childHeaderPhi, Instruction *firstNonPhiOfNewLatch,
		BasicBlock *childPreHeader, BasicBlock *newLatchBlock,
		BasicBlock *oldLatchBlock, BasicBlock *childLatch) {
	auto childBackedgeVal = childHeaderPhi.getIncomingValueForBlock(childLatch);
	PHINode *latchPhi;
	bool latchPhiIsNew = true;
	if (auto oldLatchPhi = dyn_cast<PHINode>(childBackedgeVal)) {
		if (oldLatchPhi->getParent() == newLatchBlock) {
			assert(newLatchBlock == oldLatchBlock);
			latchPhi = oldLatchPhi;
			latchPhiIsNew = false;
		}
	}
	if (latchPhiIsNew) {
		size_t phiArgCnt =
				2
						+ (mode
								== LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION);
		assert(!Ty->isPointerTy());
		latchPhi = PHINode::Create(Ty, phiArgCnt,
				childHeaderPhi.getName() + ".inLatch", firstNonPhiOfNewLatch->getIterator());
		latchPhi->addIncoming(childBackedgeVal, childLatch);
	}
	if (mode
			== LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION) {
		latchPhi->addIncoming(childHeaderPhi.getIncomingValueForBlock(childPreHeader), childPreHeader);
	}
	// errs() << "createPhiInNewLatch: " << *latchPhi << "\n";
	return {latchPhi, latchPhiIsNew};
}

static void createNewLatchPhis(const LoopFlattenUsingIfPass::Mode mode, llvm::BasicBlock *childLatch,
		BasicBlock * childPreHeader, BasicBlock *childHeader, BasicBlock *&newLatchBlock,
		MemorySSAUpdater *MSSAU, DomTreeUpdater &DTU, BasicBlock *header,
		PHINode &isChildLoopSwitchPhi, BasicBlock *oldLatchBlock) {
	SmallVector<DominatorTree::UpdateType, 2> Updates;
	Updates.push_back( { DominatorTree::Delete, childLatch, childHeader });
	Updates.push_back( { DominatorTree::Insert, childLatch, newLatchBlock });
	// DTU, MSSAU update as done in llvm::splitBlockBefore
	DTU.applyUpdates(Updates);
	DTU.flush();
	if (MSSAU) {
		MSSAU->applyUpdates(Updates, DTU.getDomTree());
	}
	IRBuilder<> Builder(newLatchBlock, newLatchBlock->getFirstNonPHIIt());
	auto &DT = DTU.getDomTree();
	for (auto &phi : header->phis()) {
		if (&phi == &isChildLoopSwitchPhi)
			continue;

		auto latchVal = phi.getIncomingValueForBlock(newLatchBlock);
		if (auto latchValI = dyn_cast<Instruction>(latchVal)) {
			auto latchValDefBB = latchValI->getParent();
			if (!DT.dominates(latchValDefBB, newLatchBlock)) {
				// create a new
				auto Ty = latchValI->getType();
				assert(!Ty->isPointerTy());
				auto newLatchPhi = Builder.CreatePHI(Ty,
						pred_size(newLatchBlock), latchValI->getName());
				if (newLatchBlock == oldLatchBlock)
					llvm_unreachable("NotImplemented");

				newLatchPhi->addIncoming(latchVal, oldLatchBlock); // if looping jumping on backedge of original loop use original
				// latch incoming value
				newLatchPhi->addIncoming(PoisonValue::get(Ty), childLatch); // undef if looping in child loop mode
				phi.setIncomingValueForBlock(newLatchBlock, newLatchPhi);
				if (mode == LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION) {
					newLatchPhi->addIncoming(PoisonValue::get(Ty), childPreHeader); // undef if jumping to child loop for the first time
					// newLatchPhi->addIncoming(latchVal, childPreHeader);
				}
				// errs() << "createNewLatchPhis: " << *newLatchPhi << "\n";
			}
		}
	}
}

static void createPhiForSwitchBetweenParentAndChildLoopInLatch(
		BasicBlock *header, BasicBlock *newLatchBlock,
		BasicBlock *childPreHeader, BasicBlock *childHeader,
		PHINode &isChildLoop, BasicBlock *oldLatchBlock) {
	auto &Ctx = header->getContext();
	auto int1Ty = IntegerType::getInt1Ty(Ctx);
	auto *isChildLoopInLatch = PHINode::Create(int1Ty, pred_size(newLatchBlock),
			"isChildLoopInLatch." + childHeader->getName(),
			newLatchBlock->getFirstNonPHIIt());
	isChildLoop.addIncoming(isChildLoopInLatch, newLatchBlock);
	bool allAreFromChildLoop = true;
	bool allAreFromParentLoop = true;
	assert(
			newLatchBlock != oldLatchBlock
					&& "Must not equal otherwise it would be impossible to between child loop backedge and exit");
	for (auto latchPred : predecessors(newLatchBlock)) {
		bool shouldJumptToChildLoop = latchPred != oldLatchBlock
				|| latchPred == childPreHeader;
		isChildLoopInLatch->addIncoming(
				ConstantInt::get(int1Ty, shouldJumptToChildLoop), latchPred);
		allAreFromChildLoop &= shouldJumptToChildLoop;
		allAreFromParentLoop &= !shouldJumptToChildLoop;
	}
	assert(
			!allAreFromChildLoop
					&& "New loop should switch between child and parent loop, something went wrong");
	assert(
			!allAreFromParentLoop
					&& "New loop should switch between child and parent loop, something went wrong");
}

/*
 * :param childPreHeader: original child loop preheader (the childHeader now has 2 because it has new edge
 *     which implements skip of parent loop begin section)
 * :param parentBeginSectionEnd: block at the end of section in parent loop which was just
 * 		made conditional, values coming from there are alloca loads if they are generated
 * 		by that section
 * */
void rerouteChildBackedgeAndTransferChildPhis(
		const LoopFlattenUsingIfPass::Mode mode, BasicBlock *childPreHeader,
		BasicBlock *childHeader, BasicBlock *extractedSectionGuard,
		llvm::Loop &LChild, BasicBlock *oldLatchBlock,
		BasicBlock *newLatchBlock, BasicBlock *parentHeader,
		llvm::Loop &LParent, PHINode *phiInLatchDrivingBranch,
		Value *valueForPhiInLatchCausingReenter, PHINode &isChildLoopSwitchPhi,
		const std::map<PHINode*, PHINode*> &associatedPhis,
		MemorySSAUpdater *MSSAU, DomTreeUpdater &DTU) {
	// :note: because we split parent latch and reroute child backedge to it
	//    some variables defined in parent loop may not dominate all uses
	//    parent header PHIs. For them we have to create a new phi in new
	//    latch block to select undef if loop executes in child loop mode.
	//    (the predecessor of new latch is a child latch)
	// newLatchBlock->getParent()->dump();
	//errs() << "rerouteChildBackedgeAndTransferChildPhis:\n";
	//errs() << "    parentHeader:";
	//parentHeader->printAsOperand(errs());
	//errs() << "\n";
	//errs() << "    childPreHeader:";
	//childPreHeader->printAsOperand(errs());
	//errs() << "\n";
	//errs() << "    oldLatchBlock:";
	//oldLatchBlock->printAsOperand(errs());
	//errs() << "\n";
	//errs() << "    newLatchBlock:";
	//newLatchBlock->printAsOperand(errs());
	//errs() << "\n";

	// reroute all continue edges in child loop to jump to newLatchBlock
	// with value asserting that it will jump to parent loop header
	//DTU.flush();
	auto childLatch = LChild.getLoopLatch();
	assert(
			childLatch
					&& "LoopSimplify normal form specifies just 1 backedge and 1 latch block");

	// for each child phi
	auto headerPredCnt = llvm::pred_size(newLatchBlock);
	auto firstNonPhiOfParentHeader = &*parentHeader->getFirstNonPHIIt();
	auto firstNonPhiOfNewLatch = &*newLatchBlock->getFirstNonPHIIt();
	auto childHeaderFirstNonPhi = childHeader->getFirstNonPHIIt();
	auto parentPreheader = LParent.getLoopPreheader();
	assert(
			parentPreheader
					&& "LoopSimplify normal form specifies that there must be preheader");

	for (PHINode &childHeaderPhi : make_early_inc_range(childHeader->phis())) {
		// create a phi in parent header which will switch between undef on enter and
		// value from prev iteration in child loop mode
		auto Ty = childHeaderPhi.getType();
		bool reusingParentHeaderPhi;
		PHINode *parentHeaderPhi;
		std::tie(parentHeaderPhi, reusingParentHeaderPhi) =
				createPhiInHeaderForChild(childHeaderPhi, associatedPhis,
						headerPredCnt, firstNonPhiOfParentHeader);
		if (!reusingParentHeaderPhi)
			// value for child loop is undef in first iteration
			// (because it is computed in child loop and it was not executed before parent loop header)
			parentHeaderPhi->addIncoming(PoisonValue::get(Ty), parentPreheader);

		PHINode *newLatchPhi;
		bool newLatchPhiIsNew;
		std::tie(newLatchPhi, newLatchPhiIsNew) = createPhiInNewLatch(mode, Ty,
				childHeaderPhi, firstNonPhiOfNewLatch, childPreHeader,
				newLatchBlock, oldLatchBlock, childLatch);

		auto valFromExtractedSection = childHeaderPhi.getIncomingValueForBlock(
				childPreHeader);
		// remove value for removed backedge
		childHeaderPhi.removeIncomingValue(childLatch);
		// add value for edge which is used if parent loop is running in child loop mode
		childHeaderPhi.addIncoming(parentHeaderPhi, extractedSectionGuard);

		auto valFromExtractedSectionAsInst = dyn_cast<LoadInst>(
				valFromExtractedSection);
		if (valFromExtractedSectionAsInst
				&& isa<AllocaInst>(
						valFromExtractedSectionAsInst->getPointerOperand())) {
			// move alloca load to this block and use it instead of this phi
			auto ld = valFromExtractedSectionAsInst->clone();
			ld->insertBefore(childHeaderFirstNonPhi);
			valFromExtractedSection = ld;
		} else {
			// the value is not generated by extracted block and we can use it instead of this phi
		}
		//childPhi.replaceAllUsesWith(valFromExtractedSection);
		//childPhi.eraseFromParent();

		// if value from extracted section is load of alloca, clone load of alloca and use it
		// else this is not variable generated by extracted section and we can use it as is
		//childPhi.addIncoming(V, BB)
		//for (int Idx = childPhi.getNumIncomingValues() - 1; Idx > 0;
		//		--Idx) {
		//	childPhi.removeIncomingValue(Idx, /*DeletePHIIfEmpty*/
		//	false);
		//}
		//for (auto _childHeadPred : predecessors(childHeader)) {
		//	if (_childHeadPred != childHeadPred) {
		//		latchPhi->addIncoming(headerPhi, _childHeadPred);
		//	}
		//}
		if (newLatchPhiIsNew) {
			// if this is new phi in new latch block add incoming values
			for (auto latchPred : predecessors(newLatchBlock)) {
				// newLatchBlock can not have childHeadPred as a predecessor
				// because it is latch and child has to have loopexit block
				// so latchPred may be childLoopExit or something after,
				// childHeader or something child prequel section which is in parent loop
				assert(latchPred != newLatchBlock);
				// value for child loop is undef once code exited child loop
				Value *V = nullptr;
				if (reusingParentHeaderPhi) {
					V = parentHeaderPhi->getIncomingValueForBlock(
							newLatchBlock);
					if (newLatchBlock == oldLatchBlock) {
						// if latch block is reused it means that the value may be defined in oldLatchBlock block,
						// it is necessary to keep define before use so if this a phi the incoming value should be used instead
						if (auto *existingLatchPhi = dyn_cast<PHINode>(V)) {
							if (existingLatchPhi->getParent() == oldLatchBlock)
								V = existingLatchPhi->getIncomingValueForBlock(
										latchPred);
							assert(V);
						} else if (auto *I = dyn_cast<Instruction>(V)) {
							assert(I->getParent() != newLatchBlock);
						}
					}
				} else {
					V = PoisonValue::get(Ty);
				}
				newLatchPhi->addIncoming(V, latchPred);
			}
		}
		if (reusingParentHeaderPhi)
			parentHeaderPhi->setIncomingValueForBlock(newLatchBlock,
					newLatchPhi);
		else
			parentHeaderPhi->addIncoming(newLatchPhi, newLatchBlock);
		if (mode == LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION) {
			childHeaderPhi.removeIncomingValue(childPreHeader);
		}
	}
	childLatch->getTerminator()->replaceSuccessorWith(childHeader,
			newLatchBlock);
	if (phiInLatchDrivingBranch) {
		assert(valueForPhiInLatchCausingReenter);
		phiInLatchDrivingBranch->addIncoming(valueForPhiInLatchCausingReenter,
				childLatch);
	}
	if (newLatchBlock == oldLatchBlock) {
		updatePhiIncommingValuesInOldLatchBlock(childLatch, oldLatchBlock,
				childHeader);
	}

	createNewLatchPhis(mode, childLatch, childPreHeader, childHeader, newLatchBlock, MSSAU, DTU,
			parentHeader, isChildLoopSwitchPhi, oldLatchBlock);
	if (mode == LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION) {
		// childPreHeader br childHeader to childPreHeader br newLatchBlock
		auto t = childPreHeader->getTerminator();
		assert(t->getNumSuccessors() == 1);
		t->setSuccessor(0, newLatchBlock);
		SmallVector<DominatorTree::UpdateType, 2> Updates;
		Updates.push_back(
				{ DominatorTree::Delete, childPreHeader, childHeader });
		Updates.push_back( { DominatorTree::Insert, childPreHeader,
				newLatchBlock });
	}
	createPhiForSwitchBetweenParentAndChildLoopInLatch(parentHeader,
			newLatchBlock, childPreHeader, childHeader, isChildLoopSwitchPhi,
			oldLatchBlock);
}

}
