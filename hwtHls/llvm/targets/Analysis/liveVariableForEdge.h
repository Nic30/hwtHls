#pragma once

#include <map>
#include <set>

#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/ADT/SetVector.h>

namespace hwtHls {

using EdgeLivenessDict = std::map<llvm::MachineBasicBlock*, std::map<llvm::MachineBasicBlock*, std::set<llvm::Register>>>;

/*
 * Get set of registers which are live on edge between two blocks.
 * Live register means that it is used by some successor block.
 * When resolving register live the input PHIs are taken in account and if the value is not selected by PHI on this path it is not live.
 * This means that this does not correspond to live variables of the block.
 * */
EdgeLivenessDict getLiveVariablesForBlockEdge(llvm::MachineRegisterInfo &MRI,
		llvm::MachineFunction &MF);

// check if instruction is some sort of immutable constant which is not required to be tracked during the liveness analysis
bool isInstructionWhichIsKeeptOutOfLiveness(llvm::MachineRegisterInfo &MRI,
		const llvm::MachineInstr &MI);

// collect which liveins and defined registers for a basic blocks
// for liveins the mbb==nullptr means that the register is required from every predecessor block
void collectDirectLiveinsAndDefines(llvm::MachineRegisterInfo &MRI,
		llvm::MachineBasicBlock &block,
		std::function<
				bool(llvm::MachineRegisterInfo &MRI,
						const llvm::MachineInstr &MI)> ignoreInstrPredicate,
		llvm::SetVector<std::pair<llvm::Register, llvm::MachineBasicBlock*>> &liveins,
		llvm::SetVector<llvm::Register> &defines);
}
