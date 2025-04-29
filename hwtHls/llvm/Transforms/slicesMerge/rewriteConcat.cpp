#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>

using namespace llvm;

namespace hwtHls {


//static llvm::BasicBlock::iterator getLaterInsertPoint(Instruction *I0,
//		Instruction *I1) {
//	if (I0 && I0->getParent() == I1->getParent() && I1->comesBefore(I0))
//		return I0->getNextNode()->getIterator();
//	else
//		return I1->getNextNode()->getIterator();
//}

template<typename T>
static bool mergeInstructionsInVector(SlicesMergeCombiner &IC,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		std::function<Value* (SlicesMergeCombiner &IC, const std::vector<T*>&)> buildReducedInstrFn) {
	assert(IC.Builder.GetInsertBlock());
	std::vector<T*> instructions;
	instructions.reserve(end - begin);

	for (auto _I = begin; _I != end; ++_I) {
		T *I = dyn_cast<T>(_I->value);
		assert(I);
		assert(_I->offset == 0);
		auto width = I->getType()->getIntegerBitWidth();
		assert(_I->width == width);
		instructions.push_back(I);
	}
	Value *widerI = buildReducedInstrFn(IC, instructions);

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	IC.assertSlicesConsistency();
	IC.verifyAfterUpdate("mergeInstructionsInVector - after buildReducedInstrFn", instructions[0]);
#endif
	if (!widerI) {
		return false; // extraction failed
	}
	assert(IC.Builder.GetInsertBlock()->end() != IC.Builder.GetInsertPoint());
	IRBuilder_setInsertPointBehindPhi(IC.Builder, &*IC.Builder.GetInsertPoint());
	assert(IC.Builder.GetInsertBlock());
	//Builder.SetInsertPoint(instructions.back());
	//Instruction *widerInstr = dyn_cast<Instruction>(widerI);
	size_t offset = 0;

	//Builder.SetInsertPoint(getLaterInsertPoint(widerInstr, instructions.back()));

	for (auto _I = begin; _I != end; ++_I) {
		SmallVector<User*> users(_I->value->users());
		for (User *U : users) {
			if (U != userToSkip) { // replace PHI with slice of the PHI if needed
				auto I = dyn_cast<Instruction>(_I->value);
				assert(I);
				auto *slice = IC.createSlice(widerI, offset, _I->width);
				assert(I != slice);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				IC.assertSlicesConsistency();
				IC.verifyAfterUpdate("mergeInstructionsInVector - before replace of part", I);
#endif
				IC.replaceInstUsesWith(*I, slice);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				IC.assertSlicesConsistency();
				IC.verifyAfterUpdate("mergeInstructionsInVector - after replace of part", I);
#endif
				break;
			}
		}
		offset += _I->width;
	}

	--end; // keep item with last I so we can place new I on this place later
	members.erase(begin, end);
	begin->value = widerI;
	begin->offset = 0;
	begin->width = widerI->getType()->getIntegerBitWidth();
	end = begin + 1; // set current end to a member behind newly added member
	return true;
}

/*
 * :note: end will point at newly added member with new PHINode
 * */
static bool mergePhisInConcatMemberVector(SlicesMergeCombiner &IC,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const Twine &Name) {
	auto createWiderPhi = [&members, &Name](SlicesMergeCombiner &IC,
			const std::vector<PHINode*> &phis) {
		return mergePhisToWiderPhi(IC.Builder, Name, phis);
	};
	return mergeInstructionsInVector<PHINode>(IC, members, begin, end,
			userToSkip, createWiderPhi);
}

static bool mergeSelectsInConcatMemberVector(SlicesMergeCombiner &IC,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const Twine &Name) {
	bool modified = false;
	auto InsertPoint = userToSkip;
	assert(InsertPoint);
	auto createWiderSelect =
			[&modified, &Name, InsertPoint](
					SlicesMergeCombiner &IC,
					const std::vector<SelectInst*> &selects) {
				BasicBlock &ParentBlock = *selects[0]->getParent();
				auto C = selects[0]->getCondition();
				Value *widerOp0 = nullptr;
				Value *widerOp1 = nullptr;
				ParallelInstVec parallelInstrOnSameVec;
				for (auto S : selects) {
					parallelInstrOnSameVec.insertSorted(S, false);
				}
				//{
				//	IRBuilderBase::InsertPointGuard guard(Builder);
				//auto *lastMemberI =
				//		const_cast<Instruction*>(parallelInstrOnSameVec.getInstructionClosesToBlockEnd());
				//assert(lastMemberI);
				//Builder.SetInsertPoint(lastMemberI->getNextNode());
				IC.Builder.SetInsertPoint(InsertPoint);
				if (!IC.extractWiderOperandsFromParallelInstructions(
						parallelInstrOnSameVec, ParentBlock,
						1, 2, widerOp0, widerOp1, modified)) {
					// extraction failed
					return (Value*) nullptr;
				}
				assert(widerOp0);
				assert(widerOp0);
				return IC.Builder.CreateSelect(C, widerOp0, widerOp1, Name);

				//}
			};
	mergeInstructionsInVector<SelectInst>(IC, members, begin, end,
			userToSkip, createWiderSelect);
	return modified;
}

// :attention: this sets the the builder insert point behind all BinOps
//             Initial insert point does not matter.
static bool mergeBinaryOperatorsInConcatMemberVector(SlicesMergeCombiner &IC,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const Twine &Name) {
	bool modified = false;
	auto InsertPoint = userToSkip;
	assert(InsertPoint);
	auto buildWidenedBinOp = [&modified, &Name, InsertPoint](SlicesMergeCombiner &IC,
			const std::vector<BinaryOperator*> &BinOps) {
		BasicBlock &ParentBlock = *BinOps[0]->getParent();
		auto opcode = Instruction::BinaryOps(BinOps[0]->getOpcode());
		Value *widerOp0 = nullptr;
		Value *widerOp1 = nullptr;
		ParallelInstVec parallelInstrOnSameVec;
		for (auto BI : BinOps) {
			parallelInstrOnSameVec.insertSorted(BI, false);
		}
		auto & Builder = IC.Builder;

		Builder.SetInsertPoint(InsertPoint);
		// :attention: this sets the the builder insert point behind all BinOps
		if (!IC.extractWiderOperandsFromParallelInstructions(
				parallelInstrOnSameVec, ParentBlock, 0, 1,
				widerOp0, widerOp1, modified)) {
			// extraction failed
			return (Value*) nullptr;
		}
		// create wider instruction just before original instruction

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		IC.assertSlicesConsistency();
		IC.verifyAfterUpdate("mergeBinaryOperatorsInConcatMemberVector - before create of merged instr", BinOps[0]);
#endif
		//if (auto widerOp0I = dyn_cast<Instruction>(widerOp0)) {
		//	if (auto widerOp1I = dyn_cast<Instruction>(widerOp1)) {
		//		Builder.SetInsertPoint(getLaterInsertPoint(widerOp0I, widerOp1I));
		//	} else {
		//		Builder.SetInsertPoint(widerOp0I);
		//	}
		//} else if (auto widerOp1I = dyn_cast<Instruction>(widerOp1)) {
		//	Builder.SetInsertPoint(widerOp1I);
		//} else {
		//	Builder.SetInsertPoint(BinOps.back()->getNextNode());
		//}
		assert(widerOp0);
		assert(widerOp1);
		Value *res;
		switch (opcode) {
		case Instruction::BinaryOps::And:
			res = Builder.CreateAnd(widerOp0, widerOp1, Name);
			break;
		case Instruction::BinaryOps::Or:
			res = Builder.CreateOr(widerOp0, widerOp1, Name);
			break;
		case Instruction::BinaryOps::Xor:
			res = Builder.CreateXor(widerOp0, widerOp1, Name);
			break;
		default:
			llvm_unreachable("NotImplemented for this type of operator");
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		IC.assertSlicesConsistency();
		IC.verifyAfterUpdate("mergeBinaryOperatorsInConcatMemberVector - aftre create of merged instr", BinOps[0]);
#endif
		return res;
	};
	mergeInstructionsInVector<BinaryOperator>(IC, members, begin, end,
			userToSkip, buildWidenedBinOp);
	return modified;
}
struct OffsetWidthValueNameGetter {
	llvm::StringRef operator()(const OffsetWidthValue &v) {
		return v.value->getName();
	}
};
// :attention: this function is called in recurse, in insert point may change
// :param I: parent concatenation which triggered this merge
bool SlicesMergeCombiner::mergeInstructionSequenceInPlace(
		llvm::SmallVector<OffsetWidthValue>::iterator mergableInstrSequenceBegin,
		llvm::SmallVector<OffsetWidthValue>::iterator &mergableInstrSequenceEnd,
		llvm::SmallVector<hwtHls::OffsetWidthValue> &members, CallInst *I) {
	// errs() << "mergeInstructionSequenceInPlace \n";
	// merge PHIs in range <phiMembersBegin, m) to a single PHI and replace them in members vector
	auto ToMerge = mergableInstrSequenceBegin->value;
	std::string name = I->getName().str();
	if (name.empty()) {
		name = resolveNameForMergedInstructions<OffsetWidthValueNameGetter>(
				make_range(mergableInstrSequenceBegin, mergableInstrSequenceEnd));
	}
	if (isa<PHINode>(ToMerge)) {
		return mergePhisInConcatMemberVector(*this, members,
				mergableInstrSequenceBegin, mergableInstrSequenceEnd, I,
				name + ".phiConc");
	} else if (isa<SelectInst>(ToMerge)) {
		return mergeSelectsInConcatMemberVector(*this, members,
				mergableInstrSequenceBegin, mergableInstrSequenceEnd, I,
				name + ".selConc");
	} else if (isa<BinaryOperator>(ToMerge)) {
		return mergeBinaryOperatorsInConcatMemberVector(*this, members,
				mergableInstrSequenceBegin, mergableInstrSequenceEnd, I,
				name + ".opConc");
	} else {
		llvm_unreachable("NotImplemented");
	}
	return false;
}
void SlicesMergeCombiner::replaceInstUsesWithBefore(llvm::Instruction &I, llvm::Value *V,
		bool excludeAssumeUsers) {
	updateSlicesBeforeReplace(I, *V);
}
Instruction* SlicesMergeCombiner::rewriteConcat(CallInst *I, bool flatten) {
	ConcatMemberVector values;
	for (auto &A : I->args()) {
		if (flatten) {
			values.push_back_flattened(A.get());
		} else {
			values.push_back(OffsetWidthValue::fromValue(A.get()));
		}
	}
	auto &members = values.members;
	auto isWorthReplacing =
			[&members](
					llvm::SmallVector<OffsetWidthValue>::iterator mergableInstrSequenceBegin,
					llvm::SmallVector<OffsetWidthValue>::iterator m) {
				// if instruction sequence is longer than 1 and contains more than 1 unique instruction
				return mergableInstrSequenceBegin != members.end()
						&& (m - mergableInstrSequenceBegin) > 1
						&& any_of(
								llvm::make_range(mergableInstrSequenceBegin + 1,
										m),
								[mergableInstrSequenceBegin](
										const OffsetWidthValue &I) {
									return I != *mergableInstrSequenceBegin;
								});
			};
	auto mergableInstrSequenceBegin = members.end();
	for (auto m = members.begin(); m != members.end(); ++m) {
		Instruction *I2 = nullptr;
		if (m->isIdentity()) {
			I2 = dyn_cast<Instruction>(m->value);
			if (I2 && (!IsBitwiseInstruction(*I2) || IsBitConcatInst(I2) || I2->use_empty())) {
				I2 = nullptr; // this instruction does not support merging
			}
			if (I2) {
				bool compatible = true;
				if (mergableInstrSequenceBegin == members.end()) {
					mergableInstrSequenceBegin = m;
				} else {
					auto *IToMergeWidth = dyn_cast<Instruction>(
							mergableInstrSequenceBegin->value);

					if (IToMergeWidth->getParent() != I2->getParent()
							|| IToMergeWidth->getOpcode() != I2->getOpcode()) {
						compatible = false;
					}
					if (compatible) {
						// same parent same type of instruction

						// if this is SelectInst check that it has the same condition
						if (auto S = dyn_cast<SelectInst>(
								mergableInstrSequenceBegin->value)) {
							auto S2 = dyn_cast<SelectInst>(I2);
							if (S->getCondition() != S2->getCondition())
								compatible = false;
						}

						if (compatible) {
							// [todo] this must be done transitively
							// :note: PHINode may have self as operand, other instructions can not
							if (!isa<PHINode>(I2)) {
								auto curentlySelected = make_range(
										mergableInstrSequenceBegin, m + 1);
								if (any_of(I2->operand_values(),
										[curentlySelected](const Value *op) {
											return any_of(curentlySelected,
													[op](
															const OffsetWidthValue &prevM) {
														return prevM.value == op;
													});
										})) {
									// if it is user of any selected value
									compatible = false;
								} else if (any_of(I2->users(),
										[curentlySelected](const User *U) {
											return any_of(curentlySelected,
													[U](
															const OffsetWidthValue &prevM) {
														return prevM.value == U;
													});
										})) {
									// if it is used by any selected value
									compatible = false;
								}
							}
						}
					}
				}
				if (compatible)
					continue; // continue to search next concatenation argument for mergable instructions
			}
		}
		// end of compatible instruction sequence detected
		if (isWorthReplacing(mergableInstrSequenceBegin, m)) {
			// merge instructions in range <mergableInstrSequenceBegin, m) to a single instruction and replace them in members vector
			Builder.SetInsertPoint(I);
			if (mergeInstructionSequenceInPlace(mergableInstrSequenceBegin, m,
					members, I)) {
				I2 = nullptr; // clean to prevent to mark end of sequence
			}
		}

		if (I2) {
			mergableInstrSequenceBegin = m;
		} else {
			mergableInstrSequenceBegin = members.end();
		}
	}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assertSlicesConsistency();
	verifyAfterUpdate("SlicesMergeCombiner::rewriteConcat before replacing", I);
#endif
	// if last item was also mergable, process leftover
	if (isWorthReplacing(mergableInstrSequenceBegin, members.end())) {
		// if instruction sequence is longer than 1 and contains more than 1 unique instruction
		// merge instructions in range <mergableInstrSequenceBegin, m)
		// to a single instruction and replace them in members vector
		auto end = members.end();
		Builder.SetInsertPoint(I);
		mergeInstructionSequenceInPlace(mergableInstrSequenceBegin, end,
				members, I);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assertSlicesConsistency();
		verifyAfterUpdate("SlicesMergeCombiner::rewriteConcat after mergeInstructionSequenceInPlace", I);
#endif
	}

	Instruction*res = nullptr;
	// the Concat can have only operands modified and rewrite may not be required
	if (values.members.size() != I->arg_size()) {
		if (!flatten)
			assert(values.members.size() < I->getNumOperands() - 1);
		Builder.SetInsertPoint(I);
		auto newI = values.resolveValue(Builder, nullptr, I);
		assert(newI != I);
		res = replaceInstUsesWith(*I, newI);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assertSlicesConsistency();
		verifyAfterUpdate("SlicesMergeCombiner::rewriteConcat after final concat resolve", I);
#endif
	}

	return res;
}

}
