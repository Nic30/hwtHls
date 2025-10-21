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

}
