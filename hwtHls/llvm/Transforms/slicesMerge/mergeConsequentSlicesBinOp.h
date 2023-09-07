#pragma once
#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/slicesMerge/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

namespace hwtHls {

bool mergeConsequentSlicesBinOp(llvm::BinaryOperator &I,
		DceWorklist::SliceDict &slices, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce);
}