#pragma once

#include <llvm/IR/PassInstrumentation.h>

namespace hwtHls {

/*
 * Register the before pass callback which acts upon hwtHls.skipPass metadata
 * and can disable execution of the passes by name. (llvm optnone disables all passes)
 * */
void registerInstrumenationHwtHlsSkipPass(
		llvm::PassInstrumentationCallbacks &PIC);

}
