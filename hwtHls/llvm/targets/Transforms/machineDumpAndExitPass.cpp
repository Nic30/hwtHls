#include <hwtHls/llvm/targets/Transforms/machineDumpAndExitPass.h>

#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>

namespace hwtHls {

char MachineDumpAndExitPass::ID = 0;

bool MachineDumpAndExitPass::runOnMachineFunction(llvm::MachineFunction &MF) {
	if (dumpFn)
		MF.dump();
	if (throwErrAndExit)
		throw IntentionalCompilationInterupt(
				"IntentionalCompilationInterupt");
	return false;
}

}
