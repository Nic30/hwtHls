#pragma once

#include <llvm/IR/PassManager.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractorIoArgUtils.h>

namespace llvm {
class Function;
class LoopInfo;
class DomTreeUpdater;
class AssumptionCache;
}

namespace hwtHls {

/**
 * A pass which merges all io instruction to a loop to one wider.
 *
 * :note: Differences:
 *     * llvm::LoadStoreVectorizer: based on Chains, which do not deal with masked stores/loads
 */
class IoPortVectorizationPass: public llvm::PassInfoMixin<IoPortVectorizationPass> {
public:

llvm::PreservedAnalyses run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM);
};

}
