#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

class IntentionalCompilationInterupt: std::exception {};
class DumpAndExitPass: public llvm::PassInfoMixin<DumpAndExitPass> {
public:
	explicit DumpAndExitPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		F.dump();
		throw IntentionalCompilationInterupt();
	}
};

}
