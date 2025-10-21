#pragma once

#define DEBUG_TYPE "hwthls-simplifycfg"

// #define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x
