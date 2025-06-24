#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>

namespace hwtHls {
bool HoistFromSwitchSuccessors(llvm::SwitchInst *SI,
		const llvm::TargetTransformInfo &TTI,
		unsigned LlvmHoistCommonSkipLimit);
}
