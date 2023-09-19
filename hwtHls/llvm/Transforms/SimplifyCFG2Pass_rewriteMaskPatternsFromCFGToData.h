#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace hwtHls {

/*
 * Detect bitmask manipulations in CFG and try rewrite them as a data operations to simplify CFG
 *
 * The goal is to gradually find which bits are directly
 * derived from some branch condition and use this bit in concatenation
 * rather than using PHI to select between numerous possible values
 *
 **/
bool SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData(
		llvm::DomTreeUpdater &DTU, llvm::BasicBlock &BBBottom);
}

