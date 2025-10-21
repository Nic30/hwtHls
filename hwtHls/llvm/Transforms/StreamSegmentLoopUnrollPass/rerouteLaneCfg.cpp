#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/rerouteLaneCfg.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/constructCodeLanesForSegments.h>

using namespace llvm;

namespace hwtHls {

void rerouteLaneCfgAndSegmentValue(IRBuilder<> &Builder, Function &F,
		DomTreeUpdater &DTU,
		const StreamChannelProps &streamProps,
		std::vector<AllocaInst*> &tmpAllocas,
		const SmallVector<Instruction*> &IoInstructions,
		const std::unique_ptr<ValueToValueMapTy[]> &valueMaps,
		std::map<BasicBlock*, unsigned> &BBToLaneIndex,
		std::map<BasicBlock*, unsigned> &BBToIndexInloopBodyCopies,
		const SmallVector<SmallVector<BasicBlock*>> &loopBodyCopies,
		const std::optional<llvm::SmallVector<int>> &allowSoFOnlyFor) {
	if (!streamProps.isOutput) {
		SmallVector<AllocaInst*> segmentValueTmps; // tmp variable for value of each segment of bus word
		buildSegmentValueTmpVars(streamProps, segmentValueTmps, F,
				*streamProps.ioArg);
		tmpAllocas.insert(tmpAllocas.end(), segmentValueTmps.begin(),
				segmentValueTmps.end());
		if (allowSoFOnlyFor.has_value()) {
			llvm_unreachable("[todo] support allowSoFOnlyFor");
		}
		//std::set<BasicBlock*> BBsWhichAreSegmentEnableCheck;
		//if (allowSoFOnlyFor.has_value()) {
		//	for (Instruction *_I : IoInstructions) {
		//		auto I = dyn_cast<LoadInst>(_I);
		//		if (!I)
		//			continue;
		//		auto BB = I->getParent();
		//		BasicBlock *TBB, *FBB;
        //
		//		BranchInst *Br = dyn_cast<BranchInst>(BB->getTerminator());
		//		if (!Br->isConditional())
		//			continue;
		//		Value *cond = Br->getCondition();
		//		if (streamProps.isStreamReadEnableOfSegment(I, cond)) {
		//			BBsWhichAreSegmentEnableCheck.insert(BB);
		//		}
        //
		//	}
		//}

		auto busWordTy = IntegerType::get(F.getContext(),
				streamProps.getWidthOfBusWord());
		size_t segmentWordWidth = busWordTy->getBitWidth()
				/ streamProps.segmentCnt;
		std::unordered_map<BasicBlock*, LoadInst*> segmentWordTmpLdForBBs;
		for (auto *I : IoInstructions) {
			replaceSegmentLoadInstWithLoadFromTmpVar(Builder, valueMaps,
					*streamProps.ioArg, busWordTy, streamProps,
					segmentWordWidth, segmentValueTmps, segmentWordTmpLdForBBs,
					BBToLaneIndex, *I);
		}
		struct NewRoutingRecord {
			BasicBlock *thisLaneSrc;
			BasicBlock *thisLaneDst;
			BasicBlock *nextLaneDst;
		};
		SmallVector<NewRoutingRecord> newRouting;
		auto getBBFromLane = [&loopBodyCopies, &BBToIndexInloopBodyCopies](size_t nextLaneI, BasicBlock *bb) {
			auto bbIndex = BBToIndexInloopBodyCopies[bb];
			return loopBodyCopies[nextLaneI][bbIndex];
		};
		for (auto *I : IoInstructions) {
			// ..figure:: _static/io_stream_segment_unroll_read.png

			// rerouteJumpsBetweenLanesToFollowSegmentIndexing
			// * start at header of last segment
			// * always jump to next lane before read
			// * backedge from original loop always jumps to head in the same segment
			// :note: I is nearly on the top of block but tmp loads is constructed before it
			for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
				Instruction *laneInstr = dyn_cast<Instruction>(
						&*valueMaps[laneI][I]);
				BasicBlock *thisLaneDst = laneInstr->getParent();
				assert(thisLaneDst);
				BasicBlock *thisLaneSrc =
						laneInstr->getParent()->getSinglePredecessor();
				assert(thisLaneSrc);
				auto nextLaneI = (laneI + 1) % streamProps.segmentCnt;
				BasicBlock *nextLaneDst = getBBFromLane(nextLaneI, thisLaneDst);;
				assert(nextLaneDst);

				// :note: can not replace immediately because getSinglePredecessor() would stop working
				newRouting.push_back(
						{ thisLaneSrc, thisLaneDst, nextLaneDst });

				// if BB is in BBsWhichAreSegmentEnableCheck and the allowSoFOnlyFor specifies that
				// the next lane can not have SoF then jump to lane which can have sof instead
				// int the branch for segment.enable==0
				// :note: thisLaneDst is in current lane,
				// :attention: the check for enable is expected to exist only in first segment read.
				//             If this is true we can safely skip the jump for such a block
				//             if the SoF is not allowed to exist in the selected lane.
				//             except for lane0 which has to remain because it loads the new word from
				//             the bus.
			}
		}
		//if (allowSoFOnlyFor.has_value()) {
		//	const llvm::SetVector<int> &allowSoFOnlyFor_ = allowSoFOnlyFor.value();
		//	for (auto * pred: predecessors(&header)) {
		//		if (L.contains(pred)) {
		//			for (size_t laneI = 0; laneI < streamProps.segmentCnt; ++laneI) {
		//				auto nextLaneI = (laneI + 1) % streamProps.segmentCnt;
		//				if (allowSoFOnlyFor_.contains(nextLaneI))
		//					continue;
		//				// find next lane which may have sof
		//				for (size_t i = 2; i < streamProps.segmentCnt; ++i) {
		//					nextLaneI = (laneI + 1) % streamProps.segmentCnt;
		//					if (allowSoFOnlyFor_.contains(nextLaneI))
		//						break;
		//				}
		//				BasicBlock *thisLaneDst = getBBFromLane(nextLaneI, &header);
		//				assert(thisLaneDst);
		//				BasicBlock *thisLaneSrc = getBBFromLane(nextLaneI, pred);
		//				assert(thisLaneSrc);
		//				BasicBlock *nextLaneDst = getBBFromLane(nextLaneI, thisLaneDst);;
		//				assert(nextLaneDst);
		//				newRouting.push_back(
		//						{ thisLaneSrc, thisLaneDst, nextLaneDst });
        //
		//			}
		//		}
		//	}
		//}
		for (auto &i : newRouting) {
			if (i.thisLaneDst != i.nextLaneDst) {
				i.thisLaneSrc->getTerminator()->replaceSuccessorWith(
						i.thisLaneDst, i.nextLaneDst);

				DTU.applyUpdates(
						{
								{ DominatorTree::Delete, i.thisLaneSrc,
										i.thisLaneDst }, //
								{ DominatorTree::Insert, i.thisLaneSrc,
										i.nextLaneDst }, });
			}

		}

		// delete original segment load instructions once they are replaced with slice of bus word
		for (auto *I : IoInstructions) {
			for (size_t laneI = 0; laneI < streamProps.segmentCnt; laneI++) {
				Instruction *laneInstr = dyn_cast<Instruction>(
						&*valueMaps[laneI][I]);
				assert(laneInstr->use_empty());
				laneInstr->eraseFromParent();
			}
		}
	} else {
		llvm_unreachable("NotImplemented - StreamSegmentLoopUnroll - output");
	}
}

}
