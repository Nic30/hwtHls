#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/InitializePasses.h>
#include <llvm/IR/InstIterator.h>
#include <llvm/IR/Instruction.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Utils/AssumeBundleBuilder.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

using namespace llvm;
namespace hwtHls {

// copied from llvm/lib/Transforms/Scalar/DCE.cpp
bool DceWorklist::DCEInstruction(Instruction *I, BasicBlock::iterator &curI) {
	if (isInstructionTriviallyDead(I, TLI)) {
		salvageDebugInfo(*I);
		salvageKnowledge(I);

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
		// advance current instruction iterator if it is not end and it is current instruction
		if (curI != BasicBlock::iterator() && I == &*curI) {
			++curI; // increment current iterator so the parent skips this remove instruction
		}

		I->eraseFromParent();

		return true;
	}
	return false;
}

bool DceWorklist::empty() const {
	return WorkList.empty();
}

void DceWorklist::insertValue(llvm::Value &V) {
	if (auto I = dyn_cast<Instruction>(&V))
		insert(*I);
}

void DceWorklist::insert(llvm::Instruction &I) {
	if (!WorkList.count(&I))
		WorkList.insert(&I);
}

bool DceWorklist::tryRemoveIfDead(llvm::Instruction &I,
		BasicBlock::iterator &curI) {
	if (!WorkList.count(&I)) {
		return DCEInstruction(&I, curI);
	}
	return false;
}

bool DceWorklist::runToCompletion(llvm::BasicBlock::iterator &curIt) {
	bool MadeChange = false;
	while (!WorkList.empty()) {
		Instruction *I = WorkList.pop_back_val();
		MadeChange |= DCEInstruction(I, curIt);
	}
	return MadeChange;
}

bool DceWorklist::runToCompletion() {
	BasicBlock::iterator it;
	return runToCompletion(it);
}

llvm::SmallSetVector<llvm::Instruction*, 16>& DceWorklist::getWorkList() {
	return WorkList;
}

}
