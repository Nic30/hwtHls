#pragma once

#include <llvm/Analysis/LoopInfo.h>

namespace hwtHls {

void mergeLlvmLoopMd(llvm::Loop &SrcL, llvm::Loop &DstL);
}
