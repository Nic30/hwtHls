#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>

#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

using namespace llvm;

namespace hwtHls {

template<typename T>
void mergeInstructionsInVector(SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		std::function<Value* (const std::vector<T*>&)> buildReducedInstrFn) {
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

	Value *widerI = buildReducedInstrFn(instructions);
	if (!widerI)
		return; // extraction failed
	Instruction *widerInstr = dyn_cast<Instruction>(widerI);
	size_t offset = 0;
	for (auto _I = begin; _I != end; ++_I) {
		for (User *U : _I->value->users()) {
			if (U != userToSkip) { // replace PHI with slice of the PHI if needed
				auto I = dyn_cast<Instruction>(_I->value);
				assert(I);
				IRBuilder<> builder(
						widerInstr && widerInstr->getParent() == I->getParent()
								&& I->comesBefore(widerInstr) ? widerInstr : I);
				IRBuilder_setInsertPointBehindPhi(builder, I);
				auto *slice = createSlice(&builder, widerI, offset, _I->width);
				I->replaceAllUsesWith(slice);
				dce.insert(*I);
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
}

/*
 * :note: end will point at newly added member with new PHINode
 * */
void mergePhisInConcatMemberVector(SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		const Twine &Name) {
	mergeInstructionsInVector<PHINode>(members, begin, end, userToSkip,
			createSlice, dce,
			[&members, &Name](const std::vector<PHINode*> &phis) {
				return mergePhisToWiderPhi(members[0].value->getContext(), Name,
						phis);
			});
}

bool mergeSelectsInConcatMemberVector(IRBuilder<> &Builder,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		const Twine &Name) {
	bool modified = false;
	mergeInstructionsInVector<SelectInst>(members, begin, end, userToSkip,
			createSlice, dce,
			[&Builder, &modified, &Name, &dce, &createSlice](
					const std::vector<SelectInst*> &selects) {
				BasicBlock &ParentBlock = *selects[0]->getParent();
				auto C = selects[0]->getCondition();
				Value *widerOp0 = nullptr;
				Value *widerOp1 = nullptr;
				ParallelInstVec parallelInstrOnSameVec;
				for (auto S : selects) {
					parallelInstrOnSameVec.insertSorted(S, false);
				}
				if (extractWiderOperandsFromParallelInstructions(
								parallelInstrOnSameVec, dce, createSlice,
								ParentBlock, 1, 2, Builder, widerOp0, widerOp1,
								modified)) {
					assert(widerOp0);
					assert(widerOp0);
					return Builder.CreateSelect(C, widerOp0, widerOp1, Name);
				} else {
					// extraction failed
					return (Value*) nullptr;
				}
			});
	return modified;
}

bool mergeBinaryOperatorsInConcatMemberVector(IRBuilder<> &Builder,
		SmallVector<OffsetWidthValue> &members,
		SmallVector<OffsetWidthValue>::iterator begin,
		SmallVector<OffsetWidthValue>::iterator &end, Instruction *userToSkip,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		const Twine &Name) {
	bool modified = false;
	mergeInstructionsInVector<BinaryOperator>(members, begin, end, userToSkip,
			createSlice, dce,
			[&Builder, &modified, &Name, &dce, &createSlice](
					const std::vector<BinaryOperator*> &BinOps) {
				BasicBlock &ParentBlock = *BinOps[0]->getParent();
				auto opcode = Instruction::BinaryOps(BinOps[0]->getOpcode());
				Value *widerOp0 = nullptr;
				Value *widerOp1 = nullptr;
				ParallelInstVec parallelInstrOnSameVec;
				for (auto BI : BinOps) {
					parallelInstrOnSameVec.insertSorted(BI, false);
				}
				if (extractWiderOperandsFromParallelInstructions(
								parallelInstrOnSameVec, dce, createSlice,
								ParentBlock, 0, 1, Builder, widerOp0, widerOp1,
								modified)) {
					assert(widerOp0);
					assert(widerOp0);
					switch (opcode) {
					case Instruction::BinaryOps::And:
						return Builder.CreateAnd(widerOp0, widerOp1, Name);
					case Instruction::BinaryOps::Or:
						return Builder.CreateOr(widerOp0, widerOp1, Name);
					case Instruction::BinaryOps::Xor:
						return Builder.CreateXor(widerOp0, widerOp1, Name);
					default:
						llvm_unreachable(
								"NotImplemented for this type of operator");
					}
				} else {
					// extraction failed
					return (Value*) nullptr;
				}
			});
	return modified;
}

void mergeInstructionSequenceInPlace(
		llvm::SmallVector<OffsetWidthValue>::iterator mergableInstrSequenceBegin,
		llvm::SmallVector<OffsetWidthValue>::iterator &mergableInstrSequenceEnd,
		const CreateBitRangeGetFn &createSlice,
		llvm::SmallVector<hwtHls::OffsetWidthValue> &members, CallInst *I,
		DceWorklist &dce, IRBuilder<> &Builder) {
	// merge PHIs in range <phiMembersBegin, m) to a single PHI and replace them in members vector
	auto ToMerge = mergableInstrSequenceBegin->value;
	if (isa<PHINode>(ToMerge)) {
		mergePhisInConcatMemberVector(members, mergableInstrSequenceBegin,
				mergableInstrSequenceEnd, I, createSlice, dce,
				I->getName() + ".phiConc");
	} else {
		if (isa<SelectInst>(ToMerge)) {
			mergeSelectsInConcatMemberVector(Builder, members,
					mergableInstrSequenceBegin, mergableInstrSequenceEnd, I,
					createSlice, dce, I->getName() + ".selConc");
		} else if (isa<BinaryOperator>(ToMerge)) {
			mergeBinaryOperatorsInConcatMemberVector(Builder, members,
					mergableInstrSequenceBegin, mergableInstrSequenceEnd, I,
					createSlice, dce, I->getName() + ".opConc");
		} else {
			llvm_unreachable("NotImplemented");
		}
	}
}

bool rewriteConcat(CallInst *I, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce, llvm::Value **_newI) {
	IRBuilder<> builder(I);
	ConcatMemberVector values(builder, nullptr);

	for (auto &A : I->args()) {
		values.push_back(OffsetWidthValue::fromValue(A.get()));
	}
	bool modified = false;
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
		if (m->offset == 0
				&& m->width == m->value->getType()->getIntegerBitWidth()) {
			I2 = dyn_cast<Instruction>(m->value);
			if (!I2 || !IsBitwiseInstruction(*I2) || IsBitConcatInst(I2)) {
				I2 = nullptr; // this instruction does not support merging
			}
			if (I2) {
				if (mergableInstrSequenceBegin == members.end()) {
					mergableInstrSequenceBegin = m;
					continue;
				} else {
					auto *IToMergeWidth = dyn_cast<Instruction>(
							mergableInstrSequenceBegin->value);
					if (IToMergeWidth->getParent() == I2->getParent()
							&& IToMergeWidth->getOpcode() == I2->getOpcode()) {
						bool compatible = false;
						if (auto S = dyn_cast<SelectInst>(
								mergableInstrSequenceBegin->value)) {
							auto S2 = dyn_cast<SelectInst>(I2);
							if (S->getCondition() == S2->getCondition())
								compatible = true;
						} else {
							compatible = true;
						}
						if (compatible)
							continue; // continue to search next concatenation argument for mergable instructions
					}
				}
			}
		}
		// end of compatible instruction sequence detected
		if (isWorthReplacing(mergableInstrSequenceBegin, m)) {
			// merge instructions in range <mergableInstrSequenceBegin, m) to a single instruction and replace them in members vector
			mergeInstructionSequenceInPlace(mergableInstrSequenceBegin, m,
					createSlice, members, I, dce, builder);
			modified = true;
			I2 = nullptr; // clean to prevent to mark end of sequence
		}

		if (I2) {
			mergableInstrSequenceBegin = m;
		} else {
			mergableInstrSequenceBegin = members.end();
		}
	}
	if (isWorthReplacing(mergableInstrSequenceBegin, members.end())) {
		// if instruction sequence is longer than 1 and contains more than 1 unique instruction
		// merge instructions in range <mergableInstrSequenceBegin, m) to a single instruction and replace them in members vector
		auto end = members.end();
		mergeInstructionSequenceInPlace(mergableInstrSequenceBegin, end,
				createSlice, members, I, dce, builder);
		modified = true;
	}

	// the Concat can have only operands modified and rewrite may not be required
	if (values.members.size() != I->getNumOperands() - 1) { // 1 for function def.
		assert(values.members.size() < I->getNumOperands() - 1);
		auto newI = values.resolveValue(I);
		if (_newI)
			*_newI = newI;
		assert(newI != I);
		I->replaceAllUsesWith(newI);
		dce.insert(*I); // can not remove immediately due to parent interators
		modified = true;
	}

	return modified;
}

}
