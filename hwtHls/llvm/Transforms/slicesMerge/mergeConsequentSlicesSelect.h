#pragma once
#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

namespace hwtHls {

bool mergeConsequentSlicesSelect(llvm::SelectInst &I,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce);
}
