#pragma once
#include <Python.h>
#include "llvm/IR/Module.h"

void runOpt(llvm::Function & fn);
