#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_tryAliginLoopBeginByPeeling.h>

#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Utils/LoopPeel.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

#define DEBUG_TYPE "StreamLoopUnroll"
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(X) { X; }

using namespace llvm;

namespace hwtHls {


// :note: same as llvm::peelLoop but it also exports peeled headers and disabled simplifyLoop
//     at the end.
//     Original intent when copying was to add additional predecessors to peeled loop headers
//     and simplifyLoop is disabled because it may modify header phis.
// :note: this implies that you should call simplifyLoop as in original after finishing updates.
bool hwtHls_peelLoop(llvm::Loop *L, unsigned PeelCount, bool PeelLast, llvm::LoopInfo *LI,
		llvm::ScalarEvolution *SE, llvm::DominatorTree &DT,
		llvm::AssumptionCache *AC, bool PreserveLCSSA,
		llvm::ValueToValueMapTy &VMap,
		llvm::SmallVector<llvm::BasicBlock*> &peeledHeaders) {
	IRBuilder<> Builder(&*L->getHeader()->getParent()->getEntryBlock().getFirstNonPHIOrDbg());
	auto tmpAlloca = Builder.CreateAlloca(Builder.getInt1Ty(), 0, "hwtHls_peelLoop_tmp");
	Builder.SetInsertPoint(&*L->getHeader()->getFirstNonPHIOrDbg());
	Builder.CreateLoad(Builder.getInt1Ty(), tmpAlloca, true);
	bool res = peelLoop(L, PeelCount, PeelLast, LI, SE, DT, AC, PreserveLCSSA, VMap);
	SmallVector<User*> tmpAllocaUsers(tmpAlloca->users());
	for (auto u: tmpAllocaUsers) {
		auto UI = dyn_cast<LoadInst>(u);
		assert(UI);
		if (UI->getParent() != L->getHeader()) {
			peeledHeaders.push_back(UI->getParent());
		}
		UI->eraseFromParent();
	}
	assert(peeledHeaders.size());
	sort(peeledHeaders, [&DT](BasicBlock *BB0, BasicBlock *BB1) {
		return DT.dominates(BB0, BB1);
	});
	tmpAlloca->eraseFromParent();
	return res;
}

LoopUnrollResult tryAliginLoopBeginByPeeling(DominatorTree &DT, LoopInfo *LI,
		ScalarEvolution &SE, const TargetLibraryInfo &TLI,
		const TargetTransformInfo &TTI, AssumptionCache &AC,
		OptimizationRemarkEmitter &ORE, bool PreserveLCSSA,
		StreamChannelProps &streamProps, Function &F, Loop *L,
		const SetVector<size_t> &entryOffsets,
		size_t minNumberOfBitsProcessedPerIteration,
		const llvm::SetVector<size_t> &_minNumberOfBitsProcessedPerIteration) {
	// resolve amount of bits taken/added from/to stream per iteration and from possible offsets of loop header resolve
	// how many times to peel and how many times to unroll to achieve desired throughput

	if (_minNumberOfBitsProcessedPerIteration.size() != 1) {
		LLVM_DEBUG(
				dbgs() << "PEELING loop %" << L->getHeader()->getName()
						<< " failed because number of bits processed"
								" by loop iteration is not constant! ("
						<< _minNumberOfBitsProcessedPerIteration.size()
						<< " values)\n");
		ORE.emit(
				[&]() {
					return OptimizationRemark(DEBUG_TYPE, "Peeling",
							L->getStartLoc(), L->getHeader())
							<< " failed because number of bits processed by loop iteration is not constant ("
							<< ore::NV("BitsPerIterationSize",
									_minNumberOfBitsProcessedPerIteration.size());
				});
	} else if (!all_of(entryOffsets,
			[&streamProps, minNumberOfBitsProcessedPerIteration](size_t off) {
				return off == 0
						|| (streamProps.dataWidth - off)
								% minNumberOfBitsProcessedPerIteration == 0;
			})) {
		// no peeling possible because number of bits which needs to be peeled is not dividable
		// by number of bits processed by the loop
		LLVM_DEBUG(
				dbgs() << "PEELING loop %" << L->getHeader()->getName()
						<< " failed because number of bits which needs to be peeled is not dividable "
								"by number of bits processed by the loop!\n");
		ORE.emit(
				[&]() {
					return OptimizationRemark(DEBUG_TYPE, "Peeling",
							L->getStartLoc(), L->getHeader())
							<< " failed because number of bits which needs to be peeled is not dividable "
									"by number of bits processed by the loop";
				});

	} else if (entryOffsets.size() == 1 && entryOffsets[0] == 0) {
		// no peeling required because loop can already start only on bit 0
	} else {
		TargetTransformInfo::PeelingPreferences PP;
		// Set the default values.
		PP.PeelCount = 0;
		PP.AllowPeeling = true;
		PP.AllowLoopNestsPeeling = false;
		PP.PeelLast = false;
		PP.PeelProfiledIterations = true;
		// can peel if the loop consumes fixed number of bits and if this number
		// of bits can be used to slice of unaligned prefix of processed data
		PP.PeelCount = 0;
		for (auto off : entryOffsets) {
			if (off != 0) {
				auto pc = (streamProps.dataWidth - off)
						/ minNumberOfBitsProcessedPerIteration;
				assert(pc != 0);
				PP.PeelCount = std::max<size_t>(PP.PeelCount, pc);
			}
		}
		assert(PP.PeelCount);

		LLVM_DEBUG(
				dbgs() << "PEELING loop %" << L->getHeader()->getName()
						<< " with iteration count " << PP.PeelCount << "!\n");
		ORE.emit(
				[&]() {
					return OptimizationRemark(DEBUG_TYPE, "Peeled",
							L->getStartLoc(), L->getHeader())
							<< " peeled loop by "
							<< ore::NV("PeelCount", PP.PeelCount)
							<< " iterations";
				});
		auto preHeader = L->getLoopPreheader();
		assert(preHeader);
		// backup values coming into loop from preheader
		//SmallVector<Value*> phiIncomingValuesFromPreheader;
		//for (auto &phi : L->getHeader()->phis()) {
		//	auto v = phi.getIncomingValueForBlock(preHeader);
		//	phiIncomingValuesFromPreheader.push_back(v);
		//}
		// :note: there are 2 methods how to make loop aligned:
		//      1. during unrolling assume it is aligned, after unrolling jump from preheader into
		//         a specific header generated by unrolling to implement processing on specific offset
		//         This however produces hard to analyze Irreducible cycle
		//      2. peel several iterations of the loop into prequel and then unroll the loop
		//         This however potentially replicates large amount of code. On the other hand
		//         this code will likely be easy to simplify.
		//   This algorithm uses method 2.
		SmallVector<BasicBlock*> peeledHeaders;
		ValueToValueMapTy VMap;
		if (hwtHls_peelLoop(L, PP.PeelCount, PP.PeelLast, LI, &SE, DT, &AC, PreserveLCSSA,
				VMap, peeledHeaders)) {
			assert(peeledHeaders.size() == PP.PeelCount);
			IRBuilder<> Builder(&F.getEntryBlock().front());
			auto dataOffVar = streamProps._getOrCreateTmpVarDataOffset(&Builder);
			CreateStreamTmpAllocaTmpSetterPlaceholder(&Builder, dataOffVar);

			// based on how many bits have to be processed in prequel jump on peeled header block in prequel section.
			auto peelBeginBB = preHeader->getUniqueSuccessor();
			assert(peelBeginBB->getUniqueSuccessor() == peeledHeaders[0]);
			DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
			SmallVector<DominatorTree::UpdateType> Updates;

			peelBeginBB->getTerminator()->eraseFromParent();
			Builder.SetInsertPoint(peelBeginBB);
			Updates.push_back( { DominatorTree::Delete, peelBeginBB,
					peeledHeaders[0] });

			auto dataOffVal = Builder.CreateLoad(dataOffVar->getAllocatedType(),
					dataOffVar);
			auto UnreachableBlock = BasicBlock::Create(F.getContext(),
					"LoopPeelSwitchUnreachable", &F);
			new UnreachableInst(F.getContext(), UnreachableBlock);

			Updates.push_back( { DominatorTree::Insert, peelBeginBB,
					UnreachableBlock });
			auto preHeadSw = Builder.CreateSwitch(dataOffVal, UnreachableBlock,
					entryOffsets.size());
			// because deleted edges may be re-added
			DTU.applyUpdates(Updates);
			DTU.flush();
			Updates.clear();

			// size_t offsetIndex = 0;
			for (size_t off : entryOffsets) {
				// :note: lowest offset means the larges number of bits to be processed thus the earlier header bb
				//      in peeled prequel to the loop (except for offset 0)
				BasicBlock *newHeader;
				if (off == 0) {
					// offset 0 means that the the processing should start from bit 0 and thus jump directly into loop
					newHeader = L->getHeader();
				} else {
					auto peelHeaderIndex = (streamProps.dataWidth
							/ minNumberOfBitsProcessedPerIteration)
							- ((streamProps.dataWidth - off)
									/ minNumberOfBitsProcessedPerIteration) - 1;
					newHeader = peeledHeaders[peelHeaderIndex];
					// ++offsetIndex;
				}
				preHeadSw->addCase(
						dyn_cast<ConstantInt>(
								ConstantInt::get(dataOffVal->getType(), off)),
						newHeader);
				Updates.push_back(
						{ DominatorTree::Insert, preHeader, newHeader });
			}
			DTU.applyUpdates(Updates);
			DTU.flush();

			simplifyLoop(L, &DT, LI, &SE, &AC, nullptr, PreserveLCSSA);
			simplifyLoopAfterUnroll(L, true, LI, &SE, &DT, &AC, &TTI);
			// If the loop was peeled, we already "used up" the profile information
			// we had, so we don't want to unroll or peel again.
			if (PP.PeelProfiledIterations)
				L->setLoopAlreadyUnrolled();
			return LoopUnrollResult::PartiallyUnrolled;
		}
	}
	return LoopUnrollResult::Unmodified;
}

}
