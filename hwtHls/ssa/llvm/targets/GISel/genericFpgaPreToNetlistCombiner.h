#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeGenericFpgaPreToNetlistCombinerPass(PassRegistry &PR);
FunctionPass* createGenericFpgaPreToNetlistCombiner();

}
