#pragma once
#include <llvm/CodeGen/MachineFunctionPass.h>
#include "../Analysis/liveVariableForEdge.h"

namespace hwtHls {

/*
 * This class just calls function passed in constructor.
 * The purpose of this class is to make all analysis accessible to a python code.
 * */
class GenericFpgaToNetlist: public llvm::MachineFunctionPass {
public:
	using MachineBasicBlockEdge = std::pair<llvm::MachineBasicBlock*, llvm::MachineBasicBlock*>;
	// MF, backedges, live_edge_variables, io_registers
	using ConvesionFnT = std::function<void(llvm::MachineFunction&,
			std::set<MachineBasicBlockEdge>&,
			EdgeLivenessDict&,
			std::vector<llvm::Register>&)>;

protected:
	ConvesionFnT conversionFn;

public:
	static char ID;
	GenericFpgaToNetlist(ConvesionFnT _conversionFn) :
			MachineFunctionPass(ID), conversionFn(_conversionFn) {
	}
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "GenericFpgaToNetlist";
	}

};

}
