#pragma once
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineLoopInfo.h>


namespace hwtHls {

/*
 * This pass concatenates livein/liveout registers on boundaries into a single register
 * to reduce number of the block.
 * */
class ConcatBlockLiveins: public llvm::MachineFunctionPass {
public:
	using MachineBasicBlockEdge = std::pair<llvm::MachineBasicBlock*, llvm::MachineBasicBlock*>;
public:
	static char ID;
	ConcatBlockLiveins() :
			MachineFunctionPass(ID){
	}
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "ConcatBlockLiveins";
	}

};

void initializeConcatBlockLiveins(llvm::PassRegistry &Registry);

}
