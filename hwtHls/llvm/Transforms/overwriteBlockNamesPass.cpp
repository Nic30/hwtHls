#include <hwtHls/llvm/Transforms/overwriteBlockNamesPass.h>

using namespace llvm;

namespace hwtHls {

llvm::PreservedAnalyses OverwriteBlockNamesPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	size_t cntr = 0;
	for (auto & BB: F)  {
		BB.setName("bb" + std::to_string(cntr++));
	}
	return PreservedAnalyses::all();
}
}
