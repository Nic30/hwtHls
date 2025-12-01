#pragma once
#include <hwtHls/llvm/llvmCompilationBundle.h>

namespace hwtHls {

/*
 * Attempt to remove as much as code as possible to create a minimal source code which causes the crash.
 * :note: The check for crash must be performed in child process.
 * 		  Forking child processes for every code modification makes this function very slow.
 * :param nprocs: max number of processes to use at once
 * */
void llvmIrStripInstrucionUnrelatedToCrash(LlvmCompilationBundle &ctx,
		size_t nprocs, std::function<void(LlvmCompilationBundle&)> testFn);

}
