#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/splitBBsOnIOAccess.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>

using namespace llvm;

namespace hwtHls {

void splitBBsOnIOAccess(DomTreeUpdater &DTU, LoopInfo &LI, Loop &L,
		Argument &IoArg, bool &ioIsInput, SmallVector<BasicBlock*> &BBs,
		SmallVector<Instruction*> &IoInstructions) {
	ioIsInput = true;
	// split blocks on LoadInst/StoreInst to this IO
	MemorySSAUpdater *MSSAU = nullptr; // not using memory ssa
	BBs.insert(BBs.end(), L.block_begin(), L.block_end());
	SmallVector<BasicBlock*> newBBs;
	Type * valueTy = nullptr;
	for (auto *BB : BBs) {
		for (auto BBIt = BB->begin(); BBIt != BB->end();) {
			std::optional<bool> shouldSplitBefore;

			if (auto Ld = dyn_cast<LoadInst>(&*BBIt)) {
				if (Ld->getPointerOperand() == &IoArg) {
					// the section for this lane will begin after the LoadInst
					// ==> the LoadInst should be at the top of BB
					shouldSplitBefore = true;
					if (valueTy != nullptr) {
						assert(valueTy == Ld->getAccessType() && "splitBBsOnIOAccess: All accesses to IO must be of the same type");
					} else {
						valueTy = Ld->getAccessType();
					}
					IoInstructions.push_back(Ld);
				}
			} else if (auto St = dyn_cast<StoreInst>(&*BBIt)) {
				if (St->getPointerOperand() == &IoArg) {
					// the section for this lane will end with this StoreInst
					shouldSplitBefore = false;
					ioIsInput = false;
					if (valueTy != nullptr) {
						assert(valueTy == St->getAccessType() && "splitBBsOnIOAccess: All accesses to IO must be of the same type");
					} else {
						valueTy = St->getAccessType();
					}
					IoInstructions.push_back(St);
				}
			}
			if (shouldSplitBefore.has_value()) {
				// :note: BasicBlock::splitBasicBlock Before=false will return new block which is after BB
				//        BasicBlock::splitBasicBlock Before=true will return new block which is before BB
				//        we should always continue in later block
				auto splitPoint = &*BBIt;
				if (!shouldSplitBefore.value())
					splitPoint = splitPoint->getNextNode();
				auto BBTmp = SplitBlock(BB, splitPoint, &DTU, &LI, MSSAU,
						BB->getName() + ".streamSegSplit",
						shouldSplitBefore.value());
				newBBs.push_back(BBTmp);
				if (shouldSplitBefore.value()) {
					assert(
							BBIt == BB->begin()
									&& "This should be the original LoadInst");
					if (Loop *L = LI.getLoopFor(BB)) {
						if (L->getHeader() == BB)
							L->moveToHeader(BBTmp); // the new block which was cut off from BB by SplitBlock is not new header
					}
				} else {
					BB = BBTmp;
					BBIt = BB->begin();
					continue; // skip ++BBIt because we are BB changed and we want to begin from first instr
				}
			}
			++BBIt;
		}
	}
	BBs.insert(BBs.end(), newBBs.begin(), newBBs.end());
}

}
