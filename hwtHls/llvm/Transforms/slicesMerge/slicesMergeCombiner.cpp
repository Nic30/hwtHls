#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

#include <llvm/IR/Verifier.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerConcatAndSlices.h>
#include <hwtHls/llvm/Transforms/utils/bitSliceInstrMove.h>

using namespace llvm;

namespace hwtHls {

void SlicesMergeCombiner::eraseFromSlices(OffsetWidthValue sliceItem,
		Instruction &I) {
	auto _slicesList = slices.find( { sliceItem.value, sliceItem.offset });
	if (_slicesList != slices.end()) {
		// the bit range get may not be registered if it was generated originally for a different bit vector
		// and during optimization the expression of base bitVector changed
		auto &slicesList = _slicesList->second;
		auto it = std::find(slicesList.begin(), slicesList.end(), &I);
		if (it != slicesList.end())
			slicesList.erase(it);
		if (slicesList.empty()) {
			slices.erase( { sliceItem.value, sliceItem.offset });
		}
	}
}

llvm::Instruction* SlicesMergeCombiner::eraseInstFromFunction(
		llvm::Instruction &I) {
	// non integer types are not expected to have bit vector slices
	if (I.getType()->isIntegerTy()) {
		OffsetWidthValue sliceItem = OffsetWidthValue::fromValue(&I);
		bool isIdentity = sliceItem.isIdentity();
		if (!isIdentity) {
			eraseFromSlices(sliceItem, I);
		}
	}
	return HwtHlsInstCombinerMixin<SlicesMergeCombiner>::eraseInstFromFunction(
			I);
}

void SlicesMergeCombiner::updateSlicesBeforeReplace(llvm::Instruction &I,
		llvm::Value &replacement) {
	assert(&I != &replacement);
	if (!I.getType()->isIntegerTy())
		return; // non integer types are not expected to have bit vector slices
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
				eraseFromSlices(sliceItem, *ui);
				if (replacementI) {
					SliceDict::key_type newKey(replacementI, sliceItem.offset);
					auto _slicesList = slices.find(newKey);
					if (_slicesList == slices.end()) {
						slices[newKey] = { ui };
					} else {
						_slicesList->second.push_back(ui);
					}
				}
			}
		}
	}
}
void SlicesMergeCombiner::assertSlicesConsistency() const {
	for (const auto &kv : slices) {
		auto I = dyn_cast<Instruction>(kv.first.first);
		assert(I);
		assert(I->getParent() && "Check that the key is not erased");
		assert(I->getParent()->getParent());
		assert(kv.second.size());
		for (auto *V : kv.second) {
			if (auto VI = dyn_cast<Instruction>(V)) {
				assert(
						VI->getParent()
								&& "Check that slice item is not erased");
				assert(VI->getParent()->getParent());

				OffsetWidthValue sliceItem = OffsetWidthValue::fromValue(V);

				if (sliceItem.value != I) {
					errs() << "    sliceValue:" << *V << "    \n"
							<< "   slicedValue:" << *sliceItem.value << "    \n"
							<< "   expectedSliced" << *I << "    "
							<< kv.first.second << "\n";
					assert(sliceItem.value == I);
				}
				assert(sliceItem.offset == kv.first.second);
			}
		}
	}
}
void SlicesMergeCombiner::verifyAfterUpdate(const char *scopeName,
		Instruction *I) {
	Module *M = F.getParent();
	std::string errTmp = scopeName;
	llvm::raw_string_ostream errSS(errTmp);
	errSS << " broken\n";
	errSS << F.getName().str();
	errSS << "\n";

	if (verifyModule(*M, &errs())) { //&errSS
		errSS << F << "\n";
		if (I)
			errSS << *I << "\n";
		assert(false);
		throw std::runtime_error(errSS.str());
	}
}

Value* SlicesMergeCombiner::createSlice(Value *bitVec, size_t lowBitNo,
		size_t bitWidth) {
	std::pair<Value*, uint64_t> key(bitVec, lowBitNo);
	auto cur = slices.find(key);
	if (cur == slices.end()) {
		// create a new slice because there is non on this vector
		auto _slice = CreateBitRangeGetConst(&Builder, bitVec, lowBitNo,
				bitWidth);
		if (auto _sliceI = dyn_cast<Instruction>(_slice)) {
			assert(isa<Instruction>(bitVec));
			if (IsBitRangeGetInst(_sliceI)) {
				slices[key] = { _sliceI };
			}
		}
		return _slice;
	} else {
		for (Instruction *sliceItem : cur->second) {
			if (auto OpVasI = dyn_cast<Instruction>(sliceItem)) {
				assert(
						OpVasI->getParent()
								&& "Check that the replacement is not erased");
				assert(OpVasI->getParent()->getParent() == &F);
			}
			if (sliceItem->getType()->getIntegerBitWidth() == bitWidth) {
				// return existing slice with proper lowBitNo, bitWidth
				return (Value*) sliceItem;
			}
		}
		// create new slice because all other slices are different than requested
		auto _slice = CreateBitRangeGetConst(&Builder, bitVec, lowBitNo,
				bitWidth);
		if (auto _sliceI = dyn_cast<Instruction>(_slice)) {
			if (IsBitRangeGetInst(_sliceI)) {
				cur->second.push_back(_sliceI);
			}
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		if (!isa<GlobalValue>(_slice)) {
			if (auto OpVasI = dyn_cast<Instruction>(_slice)) {
				assert(
						OpVasI->getParent()
								&& "Check that the replacement is not erased");
				assert(OpVasI->getParent()->getParent() == &F);
			}
		}
#endif
		return _slice;
	}
}

llvm::Instruction* SlicesMergeCombiner::runOnInstr(llvm::Instruction &I) {
	if (auto *CI = dyn_cast<CallInst>(&I)) {
		if (IsBitConcat(CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			verifyAfterUpdate("rewriteConcat received corrupted function",
					CI);
#endif
			if (auto r = tryReduceConcatToZExt(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceConcatToZExt corrupted function", r);
#endif
				return r;
			} else if (auto r = tryReduceConstOpConcat(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceConstOpConcat corrupted function", r);
#endif
				return r;
			} else if (auto r = tryReduceConcatOnConcatOrContinuousSlices(*this,
					*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceConcatOnConcatOrContinuousSlices corrupted function", r);
#endif
				return r;
			} else if (auto r = rewriteConcat(CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("rewriteConcat corrupted function", r);
#endif
				return r;
			}

		} else if (IsBitRangeGet(CI)) {
			BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(*CI);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand corrupted function", CI);
#endif
			if (auto r = tryReduceConstOpBitRangeGet(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceConstOpBitRangeGet corrupted function", r);
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnBitRangeGet(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceBitRangeGetOnBitRangeGet corrupted function", r);
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnConcat(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				verifyAfterUpdate("tryReduceBitRangeGetOnConcat corrupted function", r);
#endif
				return r;
			}
		}
	} else if (auto EI = dyn_cast<ZExtInst>(&I)) {
		if (auto r = tryReduceZExt_onZExt(*this, *EI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			verifyAfterUpdate(
					"BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand corrupted function",
					r);
#endif
			return r;
		}
	} else if (auto TI = dyn_cast<TruncInst>(&I)) {
		TruncInstMoveIntoSliceSuccessorsOfSrcOperand(*TI);
	}
	//if (auto r = simplifyInstruction(&I, SQ)) {
	//		return replaceInstUsesWith(I, r);
	//	}
	if (!slices.empty()) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
		verifyAfterUpdate("mergeConsequentSlices received corrupted function",
				&I);
#endif
		bool merged = false;
		if (auto r = mergeConsequentSlices(I, merged)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			verifyUsesList(F);
			verifyAfterUpdate("mergeConsequentSlices corrupted function", nullptr);
#endif
			return r; // user replacing etc. already done in mergeConsequentSlices
		}
	}
	return nullptr;
}

}
