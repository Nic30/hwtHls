#pragma once

#include <iostream>
#include <fstream>

#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {

void writeCFGToDotFile(llvm::MachineFunction &F, const std::string &Filename,
		bool debugMsgs = false,
		bool CFGOnly = false);

}
