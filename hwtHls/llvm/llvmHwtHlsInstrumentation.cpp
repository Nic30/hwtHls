#include <hwtHls/llvm/llvmHwtHlsInstrumentation.h>
#include <llvm/IR/Function.h>

using namespace llvm;

namespace hwtHls {

void registerInstrumenationHwtHlsSkipPass(PassInstrumentationCallbacks &PIC) {
	PIC.registerShouldRunOptionalPassCallback([](StringRef P, Any IR) {
		//if (any_cast<const Module *>(&IR))
		//  return "[module]";

		if (const auto **_F = any_cast<const Function*>(&IR)) {
			const Function &F = **_F;
			auto *md = F.getMetadata("hwtHls.skipPass");
			if (md) {
				for (auto &_passName : md->operands()) {
					auto skipedPassNameMD = dyn_cast<MDString>(_passName.get());
					assert(skipedPassNameMD);
					if (skipedPassNameMD->getString() == P) {
						// errs() << "Skipping: " << P << "\n";
						return false;
					}
				}
			}
		}

		//if (const auto **C = any_cast<const LazyCallGraph::SCC *>(&IR))
		//  return (*C)->getName();
		//
		//if (const auto **L = any_cast<const Loop *>(&IR))
		//  return (*L)->getName().str();
		return true;
	});
}

}
