#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/constructCodeLanesForSegments.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

using namespace llvm;

namespace hwtHls {

void copyCodeForLanes(const StreamChannelProps &streamProps, llvm::LoopInfo &LI,
		llvm::Loop &currentLoop, llvm::DomTreeUpdater &DTU,
		const SmallVector<BasicBlock*> &BBs,
		SmallVector<SmallVector<BasicBlock*> > &loopBodyCopies,
		const std::unique_ptr<ValueToValueMapTy[]> &valueMaps,
		llvm::Function &F) {
	loopBodyCopies.resize(streamProps.segmentCnt);
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		bool isLast = laneI == streamProps.segmentCnt - 1;
		auto &valMap = valueMaps[laneI];
		std::string nameSuffix = std::string(".") + std::to_string(laneI)
				+ "lane";
		std::map<Loop*, Loop*> clonedLoops;
		for (auto *BB : BBs) {
			BasicBlock *newBB;
			if (isLast) {
				// use original code instead of last copy
				if (BB->hasName())
					BB->setName(BB->getName() + nameSuffix);
				newBB = BB;
				for (auto &I : *BB) {
					valMap[&I] = &I;
					if (I.hasName())
						I.setName(I.getName() + nameSuffix);
				}
			} else {
				newBB = CloneBasicBlock(BB, valMap, nameSuffix);
				F.insert(BB->getIterator(), newBB);
				auto *L = LI.getLoopFor(BB);
				if (L == &currentLoop) {
					currentLoop.addBasicBlockToLoop(newBB, LI);
				} else {
					auto ExistingNewLoop = clonedLoops.find(L);
					if (ExistingNewLoop != clonedLoops.end()) {
						ExistingNewLoop->second->addBasicBlockToLoop(newBB, LI);
					} else {
						Loop *NewLoop = LI.AllocateLoop();
						clonedLoops[L] = NewLoop;
						currentLoop.addChildLoop(NewLoop);
						NewLoop->addBasicBlockToLoop(newBB, LI);
					}
				}
			}
			valMap[BB] = newBB;
			loopBodyCopies[laneI].push_back(newBB);
		}
	}
	// update operands of cloned instructions to new instructions
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		auto &valMap = valueMaps[laneI];
		ValueMapper valMapper(valMap,
				RF_NoModuleLevelChanges | RF_IgnoreMissingLocals);
		for (auto *BB : loopBodyCopies[laneI])
			for (auto &I : *BB) {
				valMapper.remapInstruction(I);
			}
	}
	// init DT for new blocks
	SmallVector<DominatorTree::UpdateType> DTUpdates;
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		auto & laneBlocks = loopBodyCopies[laneI];
		SmallPtrSet<BasicBlock*, 32> laneBlockSet;
		laneBlockSet.insert(laneBlocks.begin(), laneBlocks.end());
		for (auto *BB : loopBodyCopies[laneI]) {
			for (auto * pred: predecessors(BB)) {
				if (laneBlockSet.contains(pred))
					continue; // will be added when adding successor
				DTUpdates.push_back({ DominatorTree::Insert, pred, BB });
			}
			for (auto * succ: successors(BB)) {
				DTUpdates.push_back({ DominatorTree::Insert, BB, succ });
			}
		}
	}
	DTU.applyUpdates(DTUpdates);
}

void buildBlockIndexMaps(
		const SmallVector<SmallVector<BasicBlock*> > &loopBodyCopies,
		std::map<BasicBlock*, unsigned> &BBToIndexInloopBodyCopies,
		std::map<BasicBlock*, unsigned> &BBToLaneIndex) {
	size_t laneI = 0;
	for (const auto &laneBBs : loopBodyCopies) {
		size_t bbI = 0;
		for (auto *BB : laneBBs) {
			BBToLaneIndex[BB] = laneI;
			BBToIndexInloopBodyCopies[BB] = bbI;
			bbI++;
		}
		laneI++;
	}
}

void buildSegmentValueTmpVars(const StreamChannelProps &streamProps,
		SmallVector<AllocaInst*> &segmentValueTmps, llvm::Function &F,
		Argument &IoArg) {
	auto segmentTy = IntegerType::get(F.getContext(),
			streamProps.getWidthOfBusWord() / streamProps.segmentCnt);
	const DataLayout &DL = F.getDataLayout();
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		auto a = new AllocaInst(segmentTy, DL.getAllocaAddrSpace(), nullptr,
				IoArg.getName() + "." + std::to_string(laneI) + "segment",
				F.getEntryBlock().front().getIterator());
		segmentValueTmps.push_back(a);
	}
}

void replaceSegmentLoadInstWithLoadFromTmpVar(IRBuilder<> &Builder,
		const std::unique_ptr<ValueToValueMapTy[]> &valueMaps, Argument &IoArg,
		Type *busWordTy, const StreamChannelProps &streamProps,
		size_t segmentWordWidth,
		const SmallVector<AllocaInst*> &segmentValueTmps,
		std::unordered_map<BasicBlock*, LoadInst*> &segmentWordTmpLdForBBs,
		const std::map<BasicBlock*, unsigned> &BBToLaneIndex, Instruction &I) {
	// :note: I is from the last lane
	{
		// :note: it is expected that the block contains only I, terminator and possibly some
		//        tmp alloca stores as the instructions should be processed by splitBBsOnIOAccess
		assert(&I == &*I.getParent()->begin());
		Instruction *lane0Instr = dyn_cast<Instruction>(&*valueMaps[0][&I]);
		assert(lane0Instr);
		// :note: the section processing this segment data is placed in parent block
		//       and all after until another LoadInst for next segment
		Builder.SetInsertPoint(lane0Instr);
	}
	// construct load of word from bus in lane0 and set segementValueTmps
	LoadInst *busWordLd = Builder.CreateLoad(busWordTy, &IoArg, true);
	assert(segmentValueTmps.size() == streamProps.segmentCnt);
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		auto segmentValue = streamProps.CreateExtractSegmentValue(Builder,
				busWordLd, laneI);
		auto segmentTmpAlloca = segmentValueTmps[laneI];
		Builder.CreateStore(segmentValue, segmentTmpAlloca);
	}

	// update instruction uses in all lanes to use load from tmp variable instead
	// of original load for segment
	for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
		Instruction *laneInstr = dyn_cast<Instruction>(&*valueMaps[laneI][&I]);
		assert(laneInstr);
		for (Use &use : make_early_inc_range(laneInstr->uses())) {
			auto user = use.getUser();
			if (auto UI = dyn_cast<Instruction>(user)) {
				BasicBlock *parentBB = UI->getParent();
				auto segmentI = BBToLaneIndex.find(parentBB);
				assert(
						segmentI != BBToLaneIndex.end()
								&& "segment load instruction should not have use outside of currently edited region");
				assert(
						segmentI->second == laneI
								&& "Cloned instruction should be referenced only lane for which it has been cloned");
				if (auto phi = dyn_cast<PHINode>(UI)) {
					// the value should be constructed in predecessor block
					parentBB = phi->getIncomingBlock(use);
				}
				LoadInst *newSegmentVal;
				// use segmentWordTmpLdForBBs to prevent duplicated loads of the same value in the same block
				auto segmentWordTmpLdForBB = segmentWordTmpLdForBBs.find(
						parentBB);
				if (segmentWordTmpLdForBB == segmentWordTmpLdForBBs.end()) {
					if (parentBB == laneInstr->getParent()) {
						Builder.SetInsertPoint(laneInstr);
					} else {
						Builder.SetInsertPoint(parentBB->getFirstInsertionPt());
					}
					AllocaInst *segmentTmpAlloca =
							segmentValueTmps[segmentI->second];
					newSegmentVal = Builder.CreateLoad(I.getType(),
							segmentTmpAlloca);
					segmentWordTmpLdForBBs[parentBB] = newSegmentVal;
				} else {
					newSegmentVal = segmentWordTmpLdForBB->second;
				}

				// in section for this segment, replace with load from segment tmp variable
				use.set(newSegmentVal);
			}
		}
	}
}
}
