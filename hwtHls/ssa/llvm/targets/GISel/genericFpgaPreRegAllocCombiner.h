#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeGenericFpgaPreRegAllocCombinerPass(PassRegistry &PR);
FunctionPass* createGenericFpgaPreRegAllocCombiner();

}
