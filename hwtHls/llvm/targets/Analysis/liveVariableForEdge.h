#pragma once

#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>

namespace hwtHls {
using EdgeLivenessDict = std::map<llvm::MachineBasicBlock*, std::map<llvm::MachineBasicBlock*, std::set<llvm::Register>>>;

/*
 * Get set of registers which are live on edge between two blocks.
 * Live register means that it is used by some successor block.
 * When resolving register live the input PHIs are taken in account and if the value is not selected by PHI on this path it is not live.
 * This means that this does not correspond to live variables of the block.
 * */
EdgeLivenessDict getLiveVariablesForBlockEdge(llvm::MachineFunction &MF);
}
