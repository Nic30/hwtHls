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
		if (dbgAssertConsistencyAfterEachChange && slices) {
			for (size_t lowBitI = 0;
					lowBitI < I->getType()->getIntegerBitWidth(); ++lowBitI) {
				auto curSlices = slices->find( { I, lowBitI });
				if (curSlices != slices->end()) {
					errs() << "unexpecded slice list for offset: " << lowBitI << "\n";
					for (auto sItem: curSlices->second) {
						errs() << "   " << sItem << *sItem << "\n";
					}
				}
				assert(
						curSlices == slices->end()
								&& "There must not be any because all uses should already be removed and erraseFromSlices() should clear it");
			}
		}

		OffsetWidthValue sliceItem;
		if (slices)
			sliceItem = OffsetWidthValue::fromValue(I);
		if (dbgAssertConsistencyAfterEachChange)
			assertSlicesConsistency();
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
		if (slices) {
			if (sliceItem.value != I) {
				erraseFromSlices(sliceItem, *I);
			} else if (dbgAssertConsistencyAfterEachChange) {
				for (size_t lowBitI = 0;
						lowBitI < I->getType()->getIntegerBitWidth();
						++lowBitI) {
					assert(
							slices->find( { I, lowBitI }) == slices->end()
									&& "There must not be any because all uses should already be removed and erraseFromSlices() should clear it");
				}
			}
		}
		I->eraseFromParent();
		if (dbgAssertConsistencyAfterEachChange)
			assertSlicesConsistency();
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
bool DceWorklist::runToCompletition() {
	BasicBlock::iterator it;
	return runToCompletition(it);
}

void DceWorklist::erraseFromSlices(OffsetWidthValue sliceItem, Instruction &I) {
	auto _slicesList = slices->find( { sliceItem.value, sliceItem.offset });
	if (_slicesList != slices->end()) {
		// the bit range get may not be registered if it was generated originally for a different bit vector
		// and during optimization the expression of base bitVector changed
		auto &slicesList = _slicesList->second;
		auto it = std::find(slicesList.begin(), slicesList.end(), &I);
		if (it != slicesList.end())
			slicesList.erase(it);
		if (slicesList.empty()) {
			slices->erase( { sliceItem.value, sliceItem.offset });
		}
	}
}

void DceWorklist::updateSlicesBeforeReplace(llvm::Instruction &I,
		llvm::Value &replacement) {
	assert(&I != &replacement);
	if (slices == nullptr || !I.getType()->isIntegerTy())
		return;
	assert(I.getType() == replacement.getType());
	auto *replacementI = dyn_cast<Instruction>(&replacement);
	if (replacementI) {
		assert(replacementI->getParent() && "replacement must not be removed");
		assert(
				replacementI->getParent()->getParent()
						&& "replacement must not be removed");
	}

	for (auto *u : I.users()) {
		if (auto *ui = dyn_cast<Instruction>(u)) {
			if (!ui->getType()->isIntegerTy())
				continue;
			OffsetWidthValue sliceItem = OffsetWidthValue::fromValue(ui);
			if (sliceItem.value != ui) { // if user is a slice (OffsetWidthValue was not resolved just to be orig. value)
				if (replacementI)
					assert(
							replacementI->getType()->getIntegerBitWidth() > 1
									&& "Otherwise there should be no slices");
				erraseFromSlices(sliceItem, *ui);
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
void DceWorklist::assertSlicesConsistency() const {
	if (!slices)
		return;
	for (const auto &kv : *slices) {
		auto I = dyn_cast<Instruction>(kv.first.first);
		assert(I);
		assert(I->getParent() && "Check that the key is not erased");
		assert(I->getParent()->getParent());
		assert(kv.second.size());
		for (auto *V : kv.second) {
			if (auto VI = dyn_cast<Instruction>(V)) {
				assert(VI->getParent() && "Check that slice item is not erased");
				assert(VI->getParent()->getParent());

				OffsetWidthValue sliceItem = OffsetWidthValue::fromValue(V);

				if (sliceItem.value != I) {
					errs() << "    sliceValue:" << *V << "    \n"
							<< "   slicedValue:" << *sliceItem.value << "    \n"
							<< "   expectedSliced"<< *I << "    " << kv.first.second << "\n";
					assert(sliceItem.value == I);
				}
				assert(sliceItem.offset == kv.first.second);
			}
		}
	}
}

}
