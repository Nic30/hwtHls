#pragma once
#include <llvm/IR/Instructions.h>
#include "utils.h"
#include "dceWorklist.h"

namespace hwtHls {

bool rewriteConcat(llvm::CallInst *I, const CreateBitRangeGetFn &createSlice, DceWorklist &dce);

}
