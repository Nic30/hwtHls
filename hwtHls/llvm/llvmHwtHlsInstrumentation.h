#pragma once

#include <llvm/IR/PassInstrumentation.h>
#

namespace hwtHls {

void registerInstrumenationHwtHlsSkipPass(
		llvm::PassInstrumentationCallbacks &PIC);

}
