#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/InitializePasses.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/Instruction.h>
#include <llvm/Pass.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Utils/AssumeBundleBuilder.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>

using namespace llvm;
namespace hwtHls {

// copied from llvm/lib/Transforms/Scalar/DCE.cpp
bool DCEInstruction(Instruction *I, SmallSetVector<Instruction*, 16> &WorkList, const TargetLibraryInfo *TLI,
		BasicBlock::iterator &curI, DceWorklist::SliceDict *slices) {
	if (isInstructionTriviallyDead(I, TLI)) {
		salvageDebugInfo(*I);
		salvageKnowledge(I);
		OffsetWidthValue sliceItem;
		if (slices)
			sliceItem = OffsetWidthValue::fromValue(I);
		// Null out all of the instruction's operands to see if any operand becomes
		// dead as we go.
		for (unsigned i = 0, e = I->getNumOperands(); i != e; ++i) {
			Value *OpV = I->getOperand(i);
			I->setOperand(i, nullptr);

			if (!OpV->use_empty() || I == OpV)
				continue;

			// If the operand is an instruction that became dead as we nulled out the
			// operand, and if it is 'trivially' dead, delete it in a future loop
			// iteration.
			if (Instruction *OpI = dyn_cast<Instruction>(OpV))
				if (isInstructionTriviallyDead(OpI, TLI))
					WorkList.insert(OpI);
		}
		if (I == &*curI) {
			++curI; // increment current iterator so the parent skips this remove instruction
		}
		if (slices && sliceItem.value != I) {
			auto _slicesList = slices->find( { sliceItem.value, sliceItem.offset });
			if (_slicesList != slices->end()) {
				// the bit range get may not be registered if it was generated originally for a different bit vector
				// and during optimization the expression of base bitVector changed
				auto &slicesList = _slicesList->second;
				auto it = std::find(slicesList.begin(), slicesList.end(), sliceItem.value);
				if (it != slicesList.end())
					slicesList.erase(it);
			}
		}
		I->eraseFromParent();
		return true;
	}
	return false;
}
bool DceWorklist::empty() const {
	return WorkList.empty();
}
void DceWorklist::insert(llvm::Instruction &I) {
	if (!WorkList.count(&I))
		WorkList.insert(&I);
}
bool DceWorklist::tryRemoveIfDead(llvm::Instruction &I, BasicBlock::iterator &curI) {
	if (!WorkList.count(&I)) {
		return DCEInstruction(&I, WorkList, TLI, curI, slices);
	}
	return false;
}
bool DceWorklist::runToCompletition(llvm::BasicBlock::iterator &curIt) {
	bool MadeChange = false;
	while (!WorkList.empty()) {
		Instruction *I = WorkList.pop_back_val();
		MadeChange |= DCEInstruction(I, WorkList, TLI, curIt, slices);
	}
	return MadeChange;
}

}