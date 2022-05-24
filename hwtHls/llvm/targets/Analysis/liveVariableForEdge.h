#pragma once

#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>

namespace hwtHls {
using EdgeLivenessDict = std::map<llvm::MachineBasicBlock*, std::map<llvm::MachineBasicBlock*, std::set<llvm::Register>>>;

EdgeLivenessDict getLiveVariablesForBlockEdge(llvm::MachineFunction &MF);
}
