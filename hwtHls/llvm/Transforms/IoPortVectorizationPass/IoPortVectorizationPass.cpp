#include <hwtHls/llvm/Transforms/IoPortVectorizationPass/InstructionGraph.h>
#include <hwtHls/llvm/Transforms/IoPortVectorizationPass/IoPortVectorizationPass.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#include <llvm/Support/ErrorHandling.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/Twine.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/PostDominators.h>
#include <llvm/IR/Analysis.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/TypeSize.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>

using namespace llvm;

namespace hwtHls {

struct PackedIoValVldPair {
	AllocaInst *val;
	AllocaInst *vld;
};

/// Vectorize IO operations in loop, assuming DAG partial order.
/// :param AllIOStores: Pre-collected StoreInsts in loop body (partial order
/// preserved)
/// :attention: AllIOStoresSorted must be in topological order (use
/// topologicalSortInstructions)
void vectorizeLoopIO(Loop &L, DominatorTree &DT, size_t segmentWidth,
					 ArrayRef<StoreInst *> AllIOInstr,
					 std::optional<unsigned> &laneCnt) {
	assert(!AllIOInstr.empty());
	BasicBlock *Header = L.getHeader();
	// errs() << "AllIOInstr: \n";
	// for (auto * st: AllIOInstr) {
	// 	errs() << "   " << *st << "\n";
	// }

	// Pack complementary IO ops into minimal lanes (cliques)
	auto &IoInstrAsInstrs =
		*reinterpret_cast<ArrayRef<llvm::Instruction *> *>(&AllIOInstr);
	auto IG = InstructionGraph::buildFromInstuctionsInLoopBodyOnly(
		L, IoInstrAsInstrs);
	SmallVector<SmallVector<StoreInst *, 8>> LaneMapping;
	auto &_LaneMapping =
		*reinterpret_cast<SmallVector<SmallVector<Instruction *, 8>> *>(
			&LaneMapping);
	IG.partialTopologicalSort(IoInstrAsInstrs, _LaneMapping);
	// for example sequence os stores st0, st1, st2 will

	// errs() << "Lanes: \n";
	// for (auto &nodes : LaneMapping) {
	// 	errs() << "   [";
	// 	for (auto st : nodes) {
	// 		errs() << *st << ", ";
	// 	}
	// 	errs() << "]\n";
	// }
	//  :attention: This number means the number of lanes for stores,
	//    store itself can contain multiple lanes, so stored value has
	//    NumLanes*lanesPerStore segments
	unsigned NumLanes = LaneMapping.size();
	if (NumLanes == 0 )
	assert(NumLanes >= 1);
	if (laneCnt.has_value()) {
		if (NumLanes < laneCnt.value()) {
			llvm_unreachable("[todo] construct multiple stores instead of just one");
		}
		laneCnt = std::max(laneCnt.value(), NumLanes);
	} else {
		//if (NumLanes == 1) {
		//	// this is just a sequence of 
		//	assert(AllIOInstr.size() > 1 && "Otherwise this function should not been called");
		//	auto instrs = _LaneMapping[0];
		//	_LaneMapping.clear();
		//	for (auto I: isntrs) {
		//		
		//	}
		//}
		laneCnt = NumLanes;
	}

	// Create per-lane storage: {valid_flag, value}
	auto &Ctx = Header->getContext();
	IRBuilder<> Builder(Header, Header->getFirstInsertionPt());
	SmallVector<PackedIoValVldPair> laneData;
	SmallVector<AllocaInst *> laneAllocaFlat;
	Type *StoreDataT = AllIOInstr[0]->getAccessType();
	size_t lanesPerStore = 1;
	if (StoreDataT->getIntegerBitWidth() != segmentWidth) {
		lanesPerStore = StoreDataT->getIntegerBitWidth() / (segmentWidth + 1);
		assert(lanesPerStore * (segmentWidth + 1) == StoreDataT->getIntegerBitWidth());
		StoreDataT = Builder.getIntNTy(lanesPerStore * segmentWidth);
	}
	auto laneEnTy = Builder.getIntNTy(lanesPerStore);
	for (unsigned LaneID = 0; LaneID < NumLanes; ++LaneID) {
		auto *val = Builder.CreateAlloca(StoreDataT, nullptr,
										 Twine("storeLaneData") +
											 std::to_string(LaneID));
		auto *vld = Builder.CreateAlloca(
			laneEnTy, nullptr, Twine("storeLaneVld") + std::to_string(LaneID));
		laneData.push_back({val, vld});
		laneAllocaFlat.push_back(val);
		laneAllocaFlat.push_back(vld);
		// Initialize all lanes: valid=0, value=poison
		Builder.CreateStore(ConstantInt::get(laneEnTy, 0), vld);
		Builder.CreateStore(PoisonValue::get(StoreDataT), val);
	}

	// Transform each IO op -> update its assigned lane
	Value *StreamAddr = AllIOInstr[0]->getPointerOperand();
	for (unsigned LaneID = 0; LaneID < NumLanes; ++LaneID) {
		for (unsigned OpIdx = 0; OpIdx < LaneMapping[LaneID].size(); ++OpIdx) {
			StoreInst *SI = LaneMapping[LaneID][OpIdx];
			auto &AtSI = Builder;
			AtSI.SetInsertPoint(SI);
			Value *Val = SI->getValueOperand();
			auto &lane = laneData[LaneID];
			auto w = Val->getType()->getIntegerBitWidth();
			if (w == segmentWidth) {
				AtSI.CreateStore(Val, lane.val);
				AtSI.CreateStore(ConstantInt::getTrue(Ctx), lane.vld);
			} else {
				// :note: already vectorized with the LANE_CNT=1
				assert(w == lanesPerStore * (segmentWidth + 1));
				auto segmentData = CreateBitRangeGetConst(
					&Builder, Val, 0, lanesPerStore * segmentWidth);
				auto segmentEn = CreateBitRangeGetConst(
					&Builder, Val, lanesPerStore * segmentWidth, lanesPerStore);
				AtSI.CreateStore(segmentData, lane.val);
				AtSI.CreateStore(segmentEn, lane.vld);
			}
			SI->eraseFromParent();
		}
	}

	// Emit vectorized store at latch, the data are packed in format LSB
	// data0,data1,...,vld0,vld1,... MSB

	/// :param isLatch: true if BB is latch, else if BB is exit block
	auto construtMergedStore = [&Builder, StreamAddr, &laneData, NumLanes,
								StoreDataT,
								laneEnTy](BasicBlock *BB, bool isLatch) {
		if (isLatch) {
			// for latches construct store at the end of the block
			Builder.SetInsertPoint(BB->getTerminator());
		} else {
			// for exits construct store at the beginning of the block
			Builder.SetInsertPoint(BB->getFirstInsertionPt());
		}
		auto &AtLatch = Builder;
		SmallVector<Value *> ConcatBits;
		for (unsigned LaneID = 0; LaneID < NumLanes; ++LaneID) {
			auto &lane = laneData[LaneID];
			ConcatBits.push_back(AtLatch.CreateLoad(StoreDataT, lane.val));
		}
		for (unsigned LaneID = 0; LaneID < NumLanes; ++LaneID) {
			auto &lane = laneData[LaneID];
			ConcatBits.push_back(AtLatch.CreateLoad(laneEnTy, lane.vld));
		}

		Value *WideStream = CreateBitConcat(&AtLatch, ConcatBits);
		AtLatch.CreateStore(WideStream, StreamAddr, true);
	};
	SmallPtrSet<BasicBlock *, 32> seenBBs;
	SmallVector<BasicBlock *> LatchBBs;
	L.getLoopLatches(LatchBBs);
	for (auto BB : LatchBBs) {
		if (seenBBs.count(BB))
			continue;
		seenBBs.insert(BB);
		assert(!isa<UnreachableInst>(BB->getTerminator()));
		construtMergedStore(BB, true);
	}
	SmallVector<BasicBlock *> ExitBBs;
	L.getExitBlocks(ExitBBs);
	for (auto *BB : ExitBBs) {
		if (seenBBs.count(BB))
			continue;
		if (succ_size(BB) != 1) {
			for (auto pred : predecessors(BB)) {
				assert(L.contains(pred) &&
					   "This should be always satisfied as the loop should be "
					   "in loop simplify normal form");
			}
		}
		seenBBs.insert(BB);
		if (isa<UnreachableInst>(BB->getTerminator()))
			continue;
		construtMergedStore(BB, false);
	}

	PromoteMemToReg(laneAllocaFlat, DT);
}

void normalizeStoresBeforeVectorization(IRBuilder<> &Builder,
										size_t segmentWidth,
										SmallVector<StoreInst *> &stores) {
	// it is possible that the store is already vectorized, if this is a case
	// it is possible that stores may have different type.
	// For lane mapping resolving we have to split all back to simple 1 segment
	// stores
	auto T = stores[0]->getAccessType();
	assert(T->isIntegerTy());
	if (all_of(stores, [T](StoreInst *I) { return I->getAccessType() == T; }))
		return; // no need to dissolve

	SmallVector<StoreInst *> segmentStores;
	for (auto *I : stores) {
		auto iT = I->getAccessType();
		assert(iT->isIntegerTy());
		auto w = iT->getIntegerBitWidth();
		if (w == segmentWidth ||
			w == segmentWidth +
					 1) { // +1 for case that the store has segmentEnable
			segmentStores.push_back(I);
		} else {
			assert(w % (segmentWidth + 1) == 0);
			// slice store to individual slices
			Builder.SetInsertPoint(I);
			auto v = I->getValueOperand();
			size_t segmentCnt = w / (segmentWidth + 1);
			auto ioPtr = I->getPointerOperand();
			bool isVolatile = I->isVolatile();
			for (unsigned i = 0; i < segmentCnt; ++i) {
				auto segmentData = CreateBitRangeGetConst(
					&Builder, v, i * segmentWidth, segmentWidth);
				auto segmentEn = CreateBitRangeGetConst(
					&Builder, v, segmentWidth * segmentCnt + i, 1);
				auto segmentVal =
					CreateBitConcat(&Builder, {segmentData, segmentEn});
				auto segmentStore =
					Builder.CreateStore(segmentVal, ioPtr, isVolatile);
				segmentStores.push_back(segmentStore);
			}
			I->eraseFromParent();
		}
	}
}

llvm::PreservedAnalyses
IoPortVectorizationPass::run(llvm::Function &F,
							 llvm::FunctionAnalysisManager &AM) {
	DominatorTree &DT = AM.getResult<DominatorTreeAnalysis>(F);
	// MemorySSA &MSSA = AM.getResult<MemorySSAAnalysis>(F).getMSSA();
	// PostDominatorTree &PDT = AM.getResult<PostDominatorTreeAnalysis>(F);
	LoopInfo &LI = AM.getResult<LoopAnalysis>(F);

	bool Changed = false;
	auto IoMds = HwtHlsIoMetadata_get(F);
	for (Loop *TopL : LI) {
		auto loops = TopL->getLoopsInPreorder(); // (outer most first)
		for (Loop *L : llvm::reverse(loops)) {	 //  (inner most loops first)
			// Collect IO stores externally
			for (auto &Arg : L->getHeader()->getParent()->args()) {
				auto &ioMd = IoMds[Arg.getArgNo()];
				if (ioMd.ioVectorization.has_value()) {
					SmallVector<StoreInst *> AllIOStores;
					auto &laneCnt = ioMd.ioVectorization.value().laneCnt;
					for (auto U : Arg.users()) {
						if (auto UI = dyn_cast<StoreInst>(U)) {
							if (L->contains(UI)) {
								if (LI.getLoopFor(UI->getParent()) == L) {
									AllIOStores.push_back(UI);
								}
							}
						}
					}
					if (AllIOStores.size() > 1) {
						// it is possible that the store is already vectorized,
						// if this is a case it is possible that stores may have
						// different type. For lane mapping resolving we have to
						// split all back to simple 1 segment stores
						IRBuilder<> Builder(F.getContext());
						normalizeStoresBeforeVectorization(
							Builder, ioMd.writeWordWidth, AllIOStores);

						// SmallVector<StoreInst *> AllIOStoresOrdered;
						//  topologicalSortInstructions<StoreInst>(*L,
						//  AllIOStores, AllIOStoresOrdered);
						vectorizeLoopIO(*L, DT, ioMd.writeWordWidth,
										AllIOStores, laneCnt);
						Changed = true;
					}
				}
			}
		}
	}
	if (!Changed) {
		return PreservedAnalyses::all();
	} else {
		HwtHlsIoMetadata_set(F, IoMds);
		auto PA = PreservedAnalyses();
		PA.preserveSet<CFGAnalyses>();
		PA.preserve<DominatorTreeAnalysis>();
		PA.preserve<PostDominatorTreeAnalysis>();
		PA.preserve<LoopAnalysis>();
		return PA;
	}
}

} // namespace hwtHls