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
		if (curI != BasicBlock::iterator() && I == &*curI) {
			++curI; // increment current iterator so the parent skips this remove instruction
		}
		if (slices && sliceItem.value != I) {
			erraseFromSlices(sliceItem, *I);
		}
		I->eraseFromParent();
		return true;
	}
	return false;
}
DceWorklist::SliceDict* DceWorklist::getSliceDict() {
	return slices;
}
bool DceWorklist::empty() const {
	return WorkList.empty();
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
bool DceWorklist::runToCompletition(llvm::BasicBlock::iterator &curIt) {
	bool MadeChange = false;
	while (!WorkList.empty()) {
		Instruction *I = WorkList.pop_back_val();
		MadeChange |= DCEInstruction(I, curIt);
	}
	return MadeChange;
}
void DceWorklist::erraseFromSlices(OffsetWidthValue sliceItem, Instruction & I) {
	auto _slicesList = slices->find( { sliceItem.value, sliceItem.offset });
	if (_slicesList != slices->end()) {
		// the bit range get may not be registered if it was generated originally for a different bit vector
		// and during optimization the expression of base bitVector changed
		auto &slicesList = _slicesList->second;
		auto it = std::find(slicesList.begin(), slicesList.end(),
				&I);
		if (it != slicesList.end())
			slicesList.erase(it);
		if (slicesList.empty()) {
			slices->erase( { sliceItem.value, sliceItem.offset });
		}
	}
}
void DceWorklist::updateSlicesBeforeReplace(llvm::Instruction &I,
		llvm::Value &replacement) {
	if (slices == nullptr || &I == &replacement || !I.getType()->isIntegerTy())
		return;

	auto *replacementI = dyn_cast<Instruction>(&replacement);
	for (auto *u : I.users()) {
		if (auto *ui = dyn_cast<Instruction>(u)) {
			if (!ui->getType()->isIntegerTy())
				continue;
			OffsetWidthValue sliceItem = OffsetWidthValue::fromValue(ui);
			if (sliceItem.value != ui) {
				erraseFromSlices(sliceItem, I);
				if (replacementI) {
					SliceDict::key_type newKey(replacementI, sliceItem.offset);
					auto _slicesList = slices->find(newKey);
					if (_slicesList == slices->end()) {
						(*slices)[newKey] = { ui };
					} else {
						_slicesList->second.push_back(ui);
					}
				}
			}
		}
	}
}

}
