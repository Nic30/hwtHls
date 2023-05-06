#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeHwtFpgaPreRegAllocCombinerPass(PassRegistry &PR);
FunctionPass* createHwtFpgaPreRegAllocCombiner();

}
