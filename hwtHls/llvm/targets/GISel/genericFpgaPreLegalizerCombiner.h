#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeGenericFpgaPreLegalizerCombinerPass(PassRegistry &PR);
FunctionPass* createGenericFpgaPreLegalizerCombiner();

}
