#include <llvm/PassRegistry.h>
#include <llvm/Pass.h>

namespace llvm {

void initializeHwtFpgaPreToNetlistCombinerPass(PassRegistry &PR);
FunctionPass* createHwtFpgaPreToNetlistCombiner();

}
