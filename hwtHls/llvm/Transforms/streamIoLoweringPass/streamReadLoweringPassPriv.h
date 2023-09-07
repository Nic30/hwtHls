#pragma once
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
namespace llvm {
class DominatorTree;
}

namespace hwtHls {
void finalizeStreamIoLowerig(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM, llvm::DominatorTree &DT,
		const std::vector<StreamChannelProps> &streamProps);
}
