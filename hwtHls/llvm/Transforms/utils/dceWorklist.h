#pragma once

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Instruction.h>

namespace hwtHls {

class DceWorklist {
protected:
	llvm::SmallSetVector<llvm::Instruction *, 16>
		WorkList; // main worklist containing instructions which are suspected
				  // to be dead
	llvm::TargetLibraryInfo *TLI;
	bool DCEInstruction(llvm::Instruction *I, llvm::BasicBlock::iterator &curI);

public:
	DceWorklist(llvm::TargetLibraryInfo *TLI) :
		TLI(TLI) {}
	bool empty() const;
	// calls insert for Instruction if Value is Instruction
	void insertValue(llvm::Value &V);
	// insert instruction which is suspected to be dead
	void insert(llvm::Instruction &I);
	bool tryRemoveIfDead(llvm::Instruction &I,
						 llvm::BasicBlock::iterator &curI);
	bool runToCompletion(llvm::BasicBlock::iterator &curIt);
	bool runToCompletion();
	llvm::SmallSetVector<llvm::Instruction *, 16> &getWorkList();
};

}
