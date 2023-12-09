#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesBinOp.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesSelect.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

using namespace llvm;

namespace hwtHls {

std::pair<Value*, uint64_t> getSliceOffset(Value *op0) {
	if (auto *op0CI = dyn_cast<CallInst>(op0)) {
		if (IsBitRangeGet(op0CI)) {
			auto *_op0Off = op0CI->getArgOperand(1);
			if (auto *offset = dyn_cast<ConstantInt>(_op0Off)) {
				auto offsetInt = offset->getZExtValue();
				auto *op0BitVec = op0CI->getArgOperand(0);
				return {op0BitVec, offsetInt};
			}
		}
	} else if (auto TI = dyn_cast<TruncInst>(op0)) {
		return {TI->getOperand(0), 0};
	} else if (auto C = dyn_cast<Constant>(op0)) {
		return {C, 0};
	}
	return {nullptr, 0};
}

bool IsBitwiseOperator(const BinaryOperator &I) {
	switch (I.getOpcode()) {
	case Instruction::BinaryOps::And:
	case Instruction::BinaryOps::Or:
	case Instruction::BinaryOps::Xor:
		return true;
	default:
		return false;
	}
}

bool IsBitwiseInstruction(const Instruction &I) {
	if (isa<PHINode>(&I) || isa<SelectInst>(&I))
		return true;
	if (auto BO = dyn_cast<BinaryOperator>(&I))
		return IsBitwiseOperator(*BO);
	if (auto CI = dyn_cast<CallInst>(&I))
		return IsBitConcat(CI);
	return false;
}

bool mergeConsequentSlices(Instruction &I,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce) {
	/*
	 * Merge instructions which are parallel to instruction I and are performed on a consequent slice of same bit vector
	 * */
	bool modified = false;

	if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
		if (IsBitwiseOperator(*BO))
			modified = mergeConsequentSlicesBinOp(*BO, createSlice, dce);
	}
	//else if (auto *C = dyn_cast<CallInst>(&I)) {
	//	if (IsBitConcat(C)) {
	//		uint64_t offset = 0;
	//		for (auto &O : C->args()) {
	//			uint64_t width = O->getType()->getIntegerBitWidth();
	//			uint64_t end = offset + width;
	//		}
	//	}
	//} else if (auto *PHI = dyn_cast<PHINode>(I)) {
	//
	//}
	else if (auto *SI = dyn_cast<SelectInst>(&I)) {
		modified = mergeConsequentSlicesSelect(*SI, createSlice, dce);
	}
	return modified;
}

void replaceMergedInstructions(const ParallelInstVec &parallelInstrOnSameVec,
		const CreateBitRangeGetFn &createSlice, IRBuilder<> &builder,
		Value *res, DceWorklist &dce) {
	uint64_t offset = 0;
	for (const auto &_partI : parallelInstrOnSameVec) {
		Instruction *partI = _partI.I;
		auto w = partI->getType()->getIntegerBitWidth();
		auto repl = createSlice(&builder, res, offset, w);
		if (repl != partI) {
			partI->replaceAllUsesWith(repl);
			dce.insert(*partI);
		}
		offset += w;
	}

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto &I = *parallelInstrOnSameVec[0].second;
	auto &F = *I.getParent()->getParent();
	auto &M = *F.getParent();
	std::string errTmp = "replaceMergedInstructions - replacing brokenn";
	llvm::raw_string_ostream errSS(errTmp);
	errSS << F.getName().str();
	errSS << "\n";
	if (verifyModule(M, &errSS)) {
		errSS << F << "\n";
		errSS << I << "\n";
		throw std::runtime_error(errSS.str());
	}
#endif
}

/// Search another instructions of same type in same block which has consequent slice on same bit vector as reference instruction I
/// search continues while there is compatible instruction of followng bits of probed bitvector
///
/// :param op0Suc: following slice on op0BitVec
/// :param requireWidthToMatch: allow to match instruction which does not have same operand width as op0Suc
/// :return: true if something was found
static bool collectParallelInstructionOnSameVectorFindFollowingInstr(
		DceWorklist::SliceDict &slices, ParallelInstVec &parallelInstrOnSameVec,
		const llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> &extraCheck, bool commutative,
		llvm::Value *op0BitVec, uint64_t op0Offset, uint64_t op0Width,
		size_t op0Index, llvm::Value *op1BitVec, uint64_t op1Offset,
		uint64_t op1Width, size_t op1Index, Instruction *op0Suc,
		bool requireWidthToMatch,
		DceWorklist::SliceDict::iterator op1SucSlices) {
	// for every successor slice of the operand 0 we check if there is an instruction of same type
	// on a successor slice of the the operand 1

	// Hypothetical sliced instruction may be applied multiple times with a different operands
	// on this place we are searching only for instructions which have exactly consequent slices as operands.
	// :note: it is not required for next slice to be of same width but those with the same width should be extracted first.
	auto w0 = op0Suc->getType()->getIntegerBitWidth();
	if (!requireWidthToMatch || w0 == op0Width) {
		for (Use &op0SucUse : op0Suc->uses()) {
			bool commutated = false;
			// check if use is searched operand in parent instruction
			if (op0SucUse.getOperandNo() != op0Index) {
				if (commutative && op0SucUse.getOperandNo() != op1Index) {
					commutated = true;
				} else {
					continue;
				}
			}
			auto *op0SucUser = op0SucUse.getUser();
			if (auto *op0SucUserI = dyn_cast<Instruction>(op0SucUser)) {
				if (op0SucUserI->getOpcode() == I.getOpcode()
						&& op0SucUserI->getParent() == I.getParent()
						&& extraCheck(*op0SucUserI)) {
					if (isa<Constant>(op1BitVec)) {
						auto op1opValue = op0SucUserI->getOperand(
								commutated ? op0Index : op1Index);
						if (isa<Constant>(op1opValue)) {
							parallelInstrOnSameVec.insertSorted(op0SucUserI,
									commutated);
							size_t w1 =
									op1opValue->getType()->getIntegerBitWidth();
							// find instruction on successor slices
							// [fixme] the right operand constraint for same vector does not apply
							collectParallelInstructionOnSameVector(slices,
									parallelInstrOnSameVec, I, extraCheck,
									commutative, op0BitVec, op0Offset + w0,
									op0Width, op0Index, op1BitVec,
									op1Offset + w1, op1Width, op1Index);
							return true;
						}
					} else {
						// is instruction of same type in same parent block
						for (Instruction *op1Suc : op1SucSlices->second) {
							// search if the instruction has the other operand of successor slice
							if (op1Suc
									!= op0SucUserI->getOperand(
											commutated ? op0Index : op1Index))
								continue;

							auto w1 = op1Suc->getType()->getIntegerBitWidth();
							if ((requireWidthToMatch && w1 == op1Width)
									|| (!requireWidthToMatch && w1 == w0)) {
								// check if none of instructions parallelInstrOnSameVec are used between found instruction and this
								if (parallelInstrOnSameVec.canInsert(
										op0SucUserI)) {
									parallelInstrOnSameVec.insertSorted(
											op0SucUserI, commutated);
									// find instruction on successor slices
									// [fixme] the right operand constraint for same vector does not apply
									collectParallelInstructionOnSameVector(
											slices, parallelInstrOnSameVec, I,
											extraCheck, commutative, op0BitVec,
											op0Offset + w0, op0Width, op0Index,
											op1BitVec, op1Offset + w1, op1Width,
											op1Index);
									return true;
								}
							}
						}
					}
				}
			}
		}
	}
	return false;
}

bool collectParallelInstructionOnSameVector(DceWorklist::SliceDict &slices,
		ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> &extraCheck, bool commutative,
		llvm::Value *op0BitVec, uint64_t op0Offset, uint64_t op0Width,
		size_t op0Index, llvm::Value *op1BitVec, uint64_t op1Offset,
		uint64_t op1Width, size_t op1Index) {

	auto op0asC = dyn_cast<Constant>(op0BitVec);
	auto op0SucSlices = slices.end();
	if (!op0asC) {
		op0SucSlices = slices.find( { op0BitVec, op0Offset + op0Width });
		if (op0SucSlices == slices.end())
			return false;
	}

	auto op1asC = dyn_cast<Constant>(op1BitVec);
	auto op1SucSlices = slices.end();
	if (!op1asC) {
		op1SucSlices = slices.find( { op1BitVec, op1Offset + op1Width });
		if (op1SucSlices == slices.end())
			return false;
	}
	assert(
			(!op0asC || !op1asC)
					&& "If both are constants this instruction should have already been evaluated");
	// [todo] search for select/phi with constant value operands by searching of the condition - there is a problem
	//  that we do not know the ordering of instructions and we may generate value with shuffled bits
	//  which generates additional instructions when merged value is used
	for (bool requireWidthToMatch : { true, false }) {
		if (op0asC) {
			assert(op1SucSlices != slices.end());
			// first operand is constant - use slices of second to search for matching instructions
			for (Instruction *op1Suc : op1SucSlices->second) {
				if (collectParallelInstructionOnSameVectorFindFollowingInstr(
						slices, parallelInstrOnSameVec, I, extraCheck,
						commutative, op1BitVec, op1Offset, op1Width, op1Index,
						op0BitVec, op0Offset, op0Width, op0Index, op1Suc,
						requireWidthToMatch, op0SucSlices))
					return true;
			}
		} else {
			assert(op0SucSlices != slices.end());
			for (Instruction *op0Suc : op0SucSlices->second) {
				if (collectParallelInstructionOnSameVectorFindFollowingInstr(
						slices, parallelInstrOnSameVec, I, extraCheck,
						commutative, op0BitVec, op0Offset, op0Width, op0Index,
						op1BitVec, op1Offset, op1Width, op1Index, op0Suc,
						requireWidthToMatch, op1SucSlices))
					return true;
			}
		}
	}
	return false;
}

std::pair<bool, llvm::Value*> ConcatMemberVector_resolveAndReduce(
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		IRBuilder<> &builder, ConcatMemberVector &cmv) {
	bool modified = false;
	auto *res = cmv.resolveValue(&*builder.GetInsertPoint());
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	Instruction *I = llvm::dyn_cast<Instruction>(cmv.members[0].value);
	Function *F = nullptr;
	Module *M = nullptr;
	if (I) {
		F = I->getParent()->getParent();
		M = F->getParent();
		std::string errTmp =
				"ConcatMemberVector_resolveAndReduce widerOp broken\n";
		llvm::raw_string_ostream errSS(errTmp);
		errSS << F->getName().str();
		errSS << "\n";
		if (verifyModule(*M, &errSS)) {
			errSS << *F << "\n";
			errSS << *I << "\n";
			;
			throw std::runtime_error(errSS.str());
		}
	}
#endif
	if (auto *CallI = dyn_cast<CallInst>(res)) {
		if (IsBitConcat(CallI)) {
			modified |= rewriteConcat(CallI, createSlice, dce, &res);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			if (I) {
				std::string errTmp =
						"ConcatMemberVector_resolveAndReduce widerOp 1 broken\n";
				llvm::raw_string_ostream errSS(errTmp);
				errSS << F->getName().str();
				errSS << "\n";
				if (verifyModule(*M, &errSS)) {
					errSS << *F << "\n";
					errSS << *I << "\n";
					;
					CallI->dump();
					throw std::runtime_error(errSS.str());
				}
			}
#endif
		}
	}
	return {modified, res};
}

bool condensateInstructionGroup(BasicBlock &ParentBB,
		ParallelInstVec &parallelInstrOnSameVec) {
	// try to sink other instructions between parts behind last part
	// try to hoist other instructions between parts before first part
	std::set<Instruction*> extractedInstructions;
	SetVector<Instruction*> unhoistableInstructions;
	BasicBlock * ParentBlock = nullptr;
	for (const auto &I2 : parallelInstrOnSameVec.iterUnique()) {
		extractedInstructions.insert(I2.I);
		if (ParentBlock) {
			assert(ParentBlock == I2.I->getParent() && "Each instruction must be in the same block"
					" otherwise we can not condensate them together by this alg.");
		} else {
			ParentBlock = I2.I->getParent();
		}
	}
	size_t uniqueInstrCnt = extractedInstructions.size();
	Instruction *firstParInstr = nullptr;
	Instruction *lastParInstr = nullptr;
	auto transitivelyDependsOnExtractedParInstr = [ &extractedInstructions,
			&unhoistableInstructions](Value *o) {
		if (auto I3 = dyn_cast<Instruction>(o)) {
			if (extractedInstructions.find(I3) != extractedInstructions.end())
				return true; // depends on some extracted instruction
			if (unhoistableInstructions.count(I3))
				return true; // depends on some instruction which transitively depends on extracted instruction
			return false; // save to move before first extracted instruction
		}
		return false;
	};
	size_t seenParInstrCnt = 0;
	for (Instruction &I2 : make_early_inc_range(ParentBB)) {
		if (extractedInstructions.find(&I2) != extractedInstructions.end()) {
			++seenParInstrCnt;
			if (firstParInstr == nullptr) {
				firstParInstr = &I2;
				lastParInstr = &I2;
			} else {
				lastParInstr = &I2;
				if (seenParInstrCnt == uniqueInstrCnt)
					break; // end of extracted instruction sequence
			}
		} else if (firstParInstr) {
			if (any_of(I2.operand_values(),
					transitivelyDependsOnExtractedParInstr)) {
				unhoistableInstructions.insert(&I2);
			} else {
				errs() << "I2.moveBefore(firstParInstr) " << I2 << "  " << *firstParInstr << "\n";
				if (&I2 != firstParInstr)
					I2.moveBefore(firstParInstr);
			}
		}
	}
	if (!unhoistableInstructions.empty()) {
		// iterating reversed because we ned first move dependent instructions to not breake use-def
		for (Instruction *I2 : reverse(unhoistableInstructions)) {
			if (any_of(I2->users(),
					[&extractedInstructions](User *U) {
						if (auto UI = dyn_cast<Instruction>(U))
							return extractedInstructions.find(UI)
									!= extractedInstructions.end();
						return false;
					})) {
				llvm_unreachable(
						"Can not extract parallel instruction operand because it depends on some extracted instruction."
								" This should have already been checked before calling of this function.");
			} else {
				I2->moveAfter(lastParInstr);
			}
		}
	}
	return true;
}

bool extractWiderOperandsFromParallelInstructions(
		ParallelInstVec &parallelInstrOnSameVec, DceWorklist &dce,
		const CreateBitRangeGetFn &createSlice, BasicBlock &ParentBlock,
		size_t op0Index, size_t op1Index, IRBuilder<> &Builder,
		Value *&widerOp0, Value *&widerOp1, bool &modified) {
	assert(parallelInstrOnSameVec.uniqueSize() > 1 && "Otherwise this is useless and it should not be called");
	// parallel instructions were discovered
	if (!condensateInstructionGroup(ParentBlock, parallelInstrOnSameVec))
		return false; // there is something non removable between instructions

	// construct wider operands from parallel instruction operands
	auto *lastMemberI =
			const_cast<Instruction*>(parallelInstrOnSameVec.getInstructionClosesToBlockEnd());
	Builder.SetInsertPoint(lastMemberI);
	ConcatMemberVector _widerOp0(Builder, nullptr);
	ConcatMemberVector _widerOp1(Builder, nullptr);
	for (ParallelInstVecItem &partI : parallelInstrOnSameVec) {
		auto o0 = OffsetWidthValue::fromValue(partI.I->getOperand(op0Index));
		auto o1 = OffsetWidthValue::fromValue(partI.I->getOperand(op1Index));
		if (partI.hasOperandsSwapped) {
			// commutativity handling
			std::swap(o0, o1);
		}
		_widerOp0.push_back(o0);
		_widerOp1.push_back(o1);
	}
	assert(
			_widerOp0.width() == _widerOp1.width()
					&& "Must be same because it was extracted from same instructions");
	bool _modified;
	std::tie(_modified, widerOp0) = ConcatMemberVector_resolveAndReduce(
			createSlice, dce, Builder, _widerOp0);
	modified |= _modified;
	std::tie(_modified, widerOp1) = ConcatMemberVector_resolveAndReduce(
			createSlice, dce, Builder, _widerOp1);
	modified |= _modified;

	return true;
}

std::tuple<bool, Value*, Value*> mergeConsequentSlicesExtractWiderOperads(
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		IRBuilder<> &builder, ParallelInstVec &parallelInstrOnSameVec,
		Instruction &I, std::function<bool(llvm::Instruction&)> extraCheck,
		bool commutative, size_t op0Index, size_t op1Index) {
	assert(parallelInstrOnSameVec.size() == 0 && "Intended for output");
	bool modified = false;
	Value *widerOp0 = nullptr;
	Value *widerOp1 = nullptr;
	Value *op0 = I.getOperand(op0Index);
	Value *op1 = I.getOperand(op1Index);

	Value *op0BitVec, *op1BitVec;
	uint64_t op0Offset, op1Offset;
	std::tie(op0BitVec, op0Offset) = getSliceOffset(op0);
	std::tie(op1BitVec, op1Offset) = getSliceOffset(op1);

	if (!op0BitVec || !op1BitVec) {
		// op0 or op1 are not result of any slice and are not constants
		return {false, nullptr, nullptr};
	} else {
		//assert(!op0asC && !op1asC);
		parallelInstrOnSameVec.insertSorted(&I, false);
		auto op0width = op0->getType()->getIntegerBitWidth();
		auto op1width = op1->getType()->getIntegerBitWidth();
		assert(dce.getSliceDict());
		if (collectParallelInstructionOnSameVector(*dce.getSliceDict(),
				parallelInstrOnSameVec, I, extraCheck, commutative, op0BitVec,
				op0Offset, op0width, op0Index, op1BitVec, op1Offset, op1width,
				op1Index)) {
			// parallel instructions were discovered
			if (!extractWiderOperandsFromParallelInstructions(
					parallelInstrOnSameVec, dce, createSlice, *I.getParent(),
					op0Index, op1Index, builder, widerOp0, widerOp1,
					modified)) {
				// can not extract because there is something non movable between instructions
				return {false, nullptr, nullptr};
			}
			modified = true;
		}
	}
	return {modified, widerOp0, widerOp1};
}

}
