#pragma once

#include <map>

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

namespace hwtHls {

class DceWorklist {
protected:
	llvm::SmallSetVector<llvm::Instruction*, 16> WorkList; // main worklist containing instructions which are suspected to be dead
	llvm::TargetLibraryInfo *TLI;
	bool DCEInstruction(llvm::Instruction *I, llvm::BasicBlock::iterator &curI);
public:
	DceWorklist(llvm::TargetLibraryInfo *TLI) :
			TLI(TLI) {
	}
	bool empty() const;
	void insertValue(llvm::Value &V);
	void insert(llvm::Instruction &I);
	bool tryRemoveIfDead(llvm::Instruction &I,
			llvm::BasicBlock::iterator &curI);
	bool runToCompletition(llvm::BasicBlock::iterator &curIt);
	bool runToCompletition();
	llvm::SmallSetVector<llvm::Instruction*, 16>& getWorkList();
};

}
