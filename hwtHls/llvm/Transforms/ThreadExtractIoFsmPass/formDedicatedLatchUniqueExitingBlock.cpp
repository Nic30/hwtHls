#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/formDedicatedLatchUniqueExitingBlock.h>

#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/SimplifyQuery.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>

#include <hwtHls/llvm/Transforms/utils/cfgUtils.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

namespace hwtHls {

bool isSafeToSpeculativelyExecuteBlockBody(BasicBlock &BB) {
	for (Instruction &I : BB) {
		if (I.isTerminator())
			return true;
		if (I.mayWriteToMemory() || I.mayReadFromMemory()
				|| I.mayHaveSideEffects() || !isSafeToSpeculativelyExecute(&I))
			return false;
	}
	return true;
}

/*
 * :param dstBlocks: vector with keys of dstBlockNumber to preserver ordering
 * */
void resolveNumbersOfLatchSuccessors(DomTreeUpdater &DTU, LoopInfo &LI,
		SmallVector<Loop::Edge> &ExitEdges, BasicBlock *header,
		BasicBlock *latch, DenseMap<BasicBlock*, size_t> &dstBlockNumber,
		SmallVector<BasicBlock*> &dstBlocks) {
	// resolve encoding of branch target for SwitchInst in latch block
	dstBlockNumber[header] = 0; // force to use 0 for header block for better readability
	dstBlocks.push_back(header);
	for (auto dst : successors(latch)) {
		// add successor of the latch because dstBlockNumber is to prevent potential
		// future duplication of successors for latch
		if (!dstBlockNumber.contains(dst)) {
			dstBlockNumber[dst] = dstBlockNumber.size();
			dstBlocks.push_back(dst);
		}
	}
	for (Loop::Edge &edge : ExitEdges) {
		const auto& [src, dst] = edge;
		bool dstSeen = dstBlockNumber.contains(dst);
		if (dstSeen && !dst->phis().empty()) {
			// the block has effect on phis, we can not let dst block to have
			// the latch block as predecessor several times, for this purpose
			// a new block on edge must be created
			edge.second = SplitEdge(src, dst, &DTU.getDomTree(), &LI);
		}
		if (!dstSeen) {
			dstBlockNumber[edge.second] = dstBlockNumber.size();
		}
	}
}

BasicBlock* constructMergedLatch(IRBuilder<> &Builder,  LoopInfo & LI, Loop &L,
		const SmallVector<BasicBlock*> &LoopLatches, size_t LoopExitingBBCnt,
		BasicBlock *header, BasicBlock *latch,
		SmallVector<DominatorTree::UpdateType> &dtUpdates) {
	auto newLatch = BasicBlock::Create(Builder.getContext(),
			latch->getName() + ".newLatch", latch->getParent(),
			latch->getNextNode());
	L.addBasicBlockToLoop(newLatch, LI);
	Builder.SetInsertPoint(newLatch);
	//dtUpdates.push_back(
	//		{ DominatorTree::Delete, edge.first, edge.second });

	if (LoopLatches.size() > 1) {
		// need to construct a new phi in newLatch out o header phi nodes
		for (auto &phi : header->phis()) {
			// check if phi is necessary (not necessary if the value coming from every latch is the same)
			Value *sameV = nullptr;
			for (auto latch : LoopLatches) {
				auto v = phi.getIncomingValueForBlock(latch);
				if (sameV == nullptr) {
					sameV = v;
				} else if (sameV != v) {
					sameV = nullptr;
					break;
				}
			}
			if (!sameV) {
				// create a phi to switch value from latch blocks
				// :note: this will later receive poison operands for exit blocks
				auto newPhi = Builder.CreatePHI(phi.getType(),
						LoopLatches.size() + LoopExitingBBCnt, phi.getName());
				for (auto latch : LoopLatches) {
					auto v = phi.getIncomingValueForBlock(latch);
					newPhi->addIncoming(v, latch);
				}
			}
			// update operands of phi in header
			for (auto latch : LoopLatches) {
				phi.removeIncomingValue(latch, false);
			}
			phi.addIncoming(sameV, newLatch);
		}
	} else {
		for (auto &phi : header->phis()) {
			phi.replaceIncomingBlockWith(latch, newLatch);
		}
	}
	for (auto oldLatch : LoopLatches) {
		oldLatch->getTerminator()->replaceSuccessorWith(header, newLatch);
		dtUpdates.push_back( { DominatorTree::Delete, oldLatch, header });
		if (!simplifyBranchToSameDst(oldLatch)) {
			dtUpdates.push_back( { DominatorTree::Insert, oldLatch, newLatch });
		}
	}

	// reroute latch to jump to a new latch instead of to header
	dtUpdates.push_back( { DominatorTree::Insert, newLatch, header });
	Builder.CreateBr(header);
	return newLatch;
}

ConstantData* getDstBlockNumberVal(
		const DenseMap<BasicBlock*, size_t> &dstBlockNumber,
		IntegerType *DstIndexTy, BasicBlock *dst) {
	auto _v = dstBlockNumber.find(dst);
	if (_v == dstBlockNumber.end())
		return PoisonValue::get(DstIndexTy);
	else
		return ConstantInt::get(DstIndexTy, _v->second);
}

void formDedicatedUniqueLoopExitingAndLatchBB(IRBuilder<> &Builder,
		DomTreeUpdater &DTU, LoopInfo &LI, Loop *L,
		SmallVector<AllocaInst*> &tmpAllocas) {
	SmallVector<BasicBlock*> LoopLatches;
	SmallVector<BasicBlock*> LoopExitingBBs;
	L->getLoopLatches(LoopLatches);
	L->getExitingBlocks(LoopExitingBBs);
	// first we need to know how many unique jump destinations from latch there will be
	// because we need to construct have some encoding of dst target
	SmallVector<Loop::Edge> ExitEdges;
	L->getExitEdges(ExitEdges);
	if (LoopLatches.size() == 1 && LoopExitingBBs.empty())
		return;

	auto *latch = LoopLatches[0];
	auto *header = L->getHeader();
	DenseMap<BasicBlock*, size_t> dstBlockNumber;
	SmallVector<BasicBlock*> dstBlocks;
	resolveNumbersOfLatchSuccessors(DTU, LI, ExitEdges, header, latch,
			dstBlockNumber, dstBlocks);
	// construct dst target tmp val which will be used in new latch SwitchInst
	auto *DstIndexTy = Builder.getIntNTy(log2ceil(dstBlockNumber.size()));

	// delete current loop metadata, as the latch terminator will likely change
	auto LoopID = L->getLoopID();
	L->setLoopID(nullptr);
	bool newLatchCreated = false;
	SmallVector<DominatorTree::UpdateType> dtUpdates;
	{
		auto latchBr = dyn_cast<BranchInst>(latch->getTerminator());
		if (LoopLatches.size() != 1 || !latchBr || latchBr->isConditional()) {
			latch = constructMergedLatch(Builder, LI, *L, LoopLatches,
					LoopExitingBBs.size(), header, latch, dtUpdates);
			dstBlockNumber[latch] = 0;
			newLatchCreated = false;
		}
	}
	if (LoopExitingBBs.size() != 1 || LoopExitingBBs[0] != latch) {
		// :note: latch must post-dominate all BBs in loop so it is safe
		//        jump from from exiting block to latch
		// if current latch contains some instructions with side-efect new latch block must be constructed
		if (!newLatchCreated
				&& (!latch->phis().empty()
						|| !isSafeToSpeculativelyExecuteBlockBody(*latch))) {
			// must form a new latch because original latch can not be speculated
			DTU.flush();
			latch = SplitEdge(latch, header, &DTU.getDomTree(), &LI, nullptr,
					latch->getName() + ".latch");
		}

		Builder.SetInsertPoint(header->getFirstInsertionPt());
		auto dstIndexTmp = Builder.CreateAlloca(DstIndexTy);
		Builder.CreateStore(
				getDstBlockNumberVal(dstBlockNumber, DstIndexTy, header),
				dstIndexTmp);
		tmpAllocas.push_back(dstIndexTmp);

		SmallPtrSet<BasicBlock*, 32> seenExitingBBs;
		for (Loop::Edge &edge : ExitEdges) {
			assert(
					edge.first->getParent()
							&& "exiting block should not be removed from function");
			auto *srcTer = edge.first->getTerminator();

			for (auto &PHI : edge.second->phis()) {
				PHI.replaceIncomingBlockWith(edge.first, latch);
			}

			if (!seenExitingBBs.contains(edge.first)) {
				// omit resolution of dstV as it was already resolved
				seenExitingBBs.insert(edge.first);

				assert(
						edge.first->getParent()
								&& "exiting block should not be removed from function");
				Builder.SetInsertPoint(srcTer);
				Value *dstV = nullptr;
				if (auto srcBr = dyn_cast<BranchInst>(srcTer)) {
					if (srcBr->isConditional()) {
						auto c = srcBr->getCondition();
						auto TSuc = srcBr->getSuccessor(0);
						auto T = getDstBlockNumberVal(dstBlockNumber,
								DstIndexTy, TSuc);
						auto FSuc = srcBr->getSuccessor(1);
						auto F = getDstBlockNumberVal(dstBlockNumber,
								DstIndexTy, FSuc);
						SimplifyQuery SQ(
								header->getParent()->getParent()->getDataLayout(),
								srcBr);
						SQ.DT = &DTU.getDomTree();
						dstV = simplifySelectInst(c, T, F, SQ);
						if (!dstV)
							dstV = Builder.CreateSelect(c, T, F);
					} else {
						dstV = getDstBlockNumberVal(dstBlockNumber, DstIndexTy,
								srcBr->getSuccessor(0));
					}
				} else if (auto srcSwitchInst = dyn_cast<SwitchInst>(srcTer)) {
					llvm_unreachable(
							"[todo] set dst target val based on SwitchInst");
				} else {
					llvm_unreachable(
							"formDedicatedUniqueLoopExitingAndLatchBB: Unsupported terminator in exiting block");
				}
				Builder.CreateStore(dstV, dstIndexTmp);
			}

			// for exits from exitingBB reroute jump from exitingBB to new latch
			// and add jump from latch to exit block (dst from exiting block)
			srcTer->replaceSuccessorWith(edge.second, latch);
			dtUpdates.push_back(
					{ DominatorTree::Delete, edge.first, edge.second });
			if (!simplifyBranchToSameDst(edge.first)) {
				dtUpdates.push_back(
						{ DominatorTree::Insert, edge.first, latch });
			}
		}
		// construct a new terminator in latch which will jump according to dstIndexTmp
		auto latchTerm = latch->getTerminator();
		Builder.SetInsertPoint(latchTerm);
		auto dstV = Builder.CreateLoad(DstIndexTy, dstIndexTmp);
		auto latchBr = dyn_cast<BranchInst>(latchTerm);
		assert(
				latchBr && !latchBr->isConditional()
						&& "Must be unconditional because it was converted into that format in previous code");
		assert(latchBr->getSuccessor(0) == header);
		assert(
				dstBlockNumber.size() == dstBlocks.size()
						|| dstBlockNumber.size() == dstBlocks.size() + 1);
		assert(dstBlockNumber.size());
		if (dstBlocks.size() == 1) {
			assert(dstBlockNumber.contains(header));
		} else if (dstBlocks.size() == 2) {
			Builder.CreateCondBr(dstV, dstBlocks[1], dstBlocks[0]);
			latchBr->eraseFromParent();
			dtUpdates.push_back(
					{ DominatorTree::Insert, latch, dstBlocks[1] });
		} else {
			auto unreachableBB = BasicBlock::Create(Builder.getContext(),
					"bb.unreachable", latch->getParent());
			Builder.SetInsertPoint(unreachableBB);
			Builder.CreateUnreachable();
			L->addBasicBlockToLoop(unreachableBB, LI);

			dtUpdates.push_back(
					{ DominatorTree::Insert, latch, unreachableBB });
			Builder.SetInsertPoint(latchTerm);
			auto sw = Builder.CreateSwitch(dstV, unreachableBB,
					dstBlocks.size());
			for (auto dst : dstBlocks) {
				sw->addCase(
						dyn_cast<ConstantInt>(
								getDstBlockNumberVal(dstBlockNumber, DstIndexTy,
										dst)), dst);
				if (dst != header)
					dtUpdates.push_back( { DominatorTree::Insert, latch, dst });
			}
		}
		// move loopID to newLatch terminator
		L->setLoopID(LoopID);

		DTU.applyUpdates(dtUpdates);
	}
}

void formDedicatedUniqueLoopExitingAndLatchBB(IRBuilder<> &Builder,
		DomTreeUpdater &DTU, LoopInfo &LI) {
	SmallVector<AllocaInst*> tmpAllocas;
	for (Loop *L : LI.getLoopsInPreorder()) {
		formDedicatedUniqueLoopExitingAndLatchBB(Builder, DTU, LI, L,
				tmpAllocas);
	}
	PromoteMemToReg(tmpAllocas, DTU.getDomTree(), nullptr);
}

}
