#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeHwtFpgaPreLegalizerCombinerPass(PassRegistry &PR);
FunctionPass* createHwtFpgaPreLegalizerCombiner();

}
