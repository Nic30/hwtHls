#pragma once

#include <map>

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

namespace hwtHls {

class DceWorklist {
public:
	// (bit vector, offset of slice) to slices of this vector beginning on this offset
	// :note: we do not need reverse dictionary, because instruction can be analyzed by OffsetWidthValue::fromValue and
	//        thus key for slice can be found
	using SliceDict = std::map<std::pair<llvm::Value*, uint64_t>, std::vector<llvm::Instruction*>>;

protected:
	llvm::SmallSetVector<llvm::Instruction*, 16> WorkList; // main worklist containing instructions which are suspected to be dead
	llvm::TargetLibraryInfo *TLI;
	SliceDict *slices; // temporary dictionary to speed up lookup of bit vector slices
	bool DCEInstruction(llvm::Instruction *I, llvm::BasicBlock::iterator &curI);
public:
	/*
	 * :param slices: optional dictionary which is used to speedup bit vector slice lookup (it may be updated by this class)
	 * */
	DceWorklist(llvm::TargetLibraryInfo *TLI, SliceDict *slices) :
			TLI(TLI), slices(slices) {
	}
	SliceDict * getSliceDict();
	bool empty() const;
	void insert(llvm::Instruction &I);
	bool tryRemoveIfDead(llvm::Instruction &I, llvm::BasicBlock::iterator &curI);
	bool runToCompletition(llvm::BasicBlock::iterator &curIt);
	bool runToCompletition();
	void erraseFromSlices(hwtHls::OffsetWidthValue sliceItem, llvm::Instruction & I);
	void updateSlicesBeforeReplace(llvm::Instruction &I, llvm::Value & replacement);
};

}
