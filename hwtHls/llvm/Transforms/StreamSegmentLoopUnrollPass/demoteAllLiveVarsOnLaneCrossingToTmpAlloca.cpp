#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/demoteAllLiveVarsOnLaneCrossingToTmpAlloca.h>
#include <llvm/Transforms/Utils/Local.h>

using namespace llvm;

namespace hwtHls {

void demoteAllLiveVarsOnLaneCrossingToTmpAlloca(llvm::IRBuilder<> &Builder,
		llvm::Function &F, bool ioIsInput,
		std::map<llvm::BasicBlock*, llvm::SetVector<llvm::Instruction*>> &allLiveins,
		const SmallVector<BasicBlock*> &_BBs,
		const llvm::SmallVector<llvm::Instruction*> &IoInstructions,
		std::vector<llvm::AllocaInst*> &tmpAllocas) {

	SetVector<BasicBlock*> BBs;
	BBs.insert(_BBs.begin(), _BBs.end());
	SetVector<Instruction*> IoInstructionsSet;
	IoInstructionsSet.insert(IoInstructions.begin(), IoInstructions.end());

	for (auto *I : IoInstructions) {
		if (ioIsInput) {
			const auto &BBLiveins = allLiveins.find(I->getParent());
			for (auto *livein : BBLiveins->second) {
				if (Instruction *liveinInst = dyn_cast<Instruction>(livein)) {
					if (BBs.contains(liveinInst->getParent()) && !IoInstructionsSet.contains(liveinInst)) {
						// :note: liveinInst are handled separately during lane cfg retouting
						auto a = DemoteRegToStack(*liveinInst);
						tmpAllocas.push_back(a);
					}
				}
			}
		} else {
			llvm_unreachable("[todo] support for output");
		}
	}
}

void demoteBlockPHIsToAlloca(std::vector<AllocaInst*> &tmpAllocas,
		BasicBlock &BB) {
	for (auto &headerPhi : make_early_inc_range(BB.phis())) {
		AllocaInst *a = DemotePHIToStack(&headerPhi);
		tmpAllocas.push_back(a);
	}
}
void demoteBlockPHIsToAlloca(std::vector<AllocaInst *> &tmpAllocas, Loop &L) {
	// :note: the PHIs are known to be only in header, other split point do
	// not have PHIs
	//  because the split was just created using SplitBlock on the place
	//  where Load/Store inst was
	demoteBlockPHIsToAlloca(tmpAllocas, *L.getHeader());
	SmallVector<BasicBlock *> ExitBlocks;
	L.getExitBlocks(ExitBlocks);
	for (auto E : ExitBlocks) {
		demoteBlockPHIsToAlloca(tmpAllocas, *E);
	}
}

}
