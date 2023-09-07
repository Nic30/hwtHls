#pragma once
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineLoopInfo.h>

#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>

namespace hwtHls {

/*
 * This class just calls function passed in constructor.
 * The purpose of this class is to make all analysis accessible to a python code.
 * */
class HwtFpgaToNetlist: public llvm::MachineFunctionPass {
public:
	using MachineBasicBlockEdge = std::pair<llvm::MachineBasicBlock*, llvm::MachineBasicBlock*>;
	// MF,
	// backedges (CFG transitions from loop body to its header),
	// liveEdgeVariables (set of registers alive on specific CFG transition),
	// ioRegisters (a register for each argument of a function),
	// registerTypes (a bitwidth for register if specified)
	// loops (information)
	using ConvesionFnT = std::function<void(llvm::MachineFunction& MF,
			std::set<MachineBasicBlockEdge>& backedges,
			hwtHls::EdgeLivenessDict& liveEdgeVariables,
			std::vector<llvm::Register>& ioRegisters,
			std::map<llvm::Register, unsigned> & registerTypes,
			llvm::MachineLoopInfo & loops
			)>;

public:
	static char ID;
	HwtFpgaToNetlist() :
			MachineFunctionPass(ID){
	}
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "HwtFpgaToNetlist";
	}

};

void initializeHwtFpgaToNetlist(llvm::PassRegistry &Registry);

}
