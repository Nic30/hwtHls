#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/slicesMergeCombiner.h>

using namespace llvm;

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>
#endif

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



Instruction* SlicesMergeCombiner::mergeConsequentSlices(Instruction &I) {
	if (I.getType()->isIntegerTy()) {
		if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
			assert(!I.use_empty());
			if (auto o0c = dyn_cast<Constant>(I.getOperand(0))) {
				if (auto o1c = dyn_cast<Constant>(I.getOperand(1))) {
					// cover the case with constant operands
					auto replacement = ConstantFoldBinaryInstruction(
							I.getOpcode(), o0c, o1c);
					updateSlicesBeforeReplace(I, *replacement);
					return replaceInstUsesWith(I, replacement);
				}
			}
			if (IsBitwiseOperator(*BO))
				return mergeConsequentSlicesBinOp(*BO);

		// } else if (auto *C = dyn_cast<CallInst>(&I)) {
		//	if (IsBitConcat(C)) {
		//		uint64_t offset = 0;
		//		for (auto &O : C->args()) {
		//			uint64_t width = O->getType()->getIntegerBitWidth();
		//			uint64_t end = offset + width;
		//		}
		//	}
		//} else if (auto *PHI = dyn_cast<PHINode>(I)) {
		//
		//
		} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
			assert(!I.use_empty());
			return mergeConsequentSlicesSelect(*SI);
		}
	}
	return nullptr;
}

struct ParallelInstVecItemNameGetter {
	StringRef operator()(const ParallelInstVecItem& I) {
		return I.I->getName();
	}
};
void SlicesMergeCombiner::replaceMergedInstructions(const ParallelInstVec &parallelInstrOnSameVec,
		Value *res) {
	uint64_t offset = 0;

	for (const ParallelInstVecItem &_partI : parallelInstrOnSameVec) {
		Instruction *partI = _partI.I;
		auto w = partI->getType()->getIntegerBitWidth();

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		verifyUsesList(F);
#endif
		// :note: builder insert point is expected to be on res or after
		auto repl = createSlice(res, offset, w);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		if (!isa<GlobalValue>(repl)) {
			if (auto OpVasI = dyn_cast<Instruction>(repl)) {
				assert(
						OpVasI->getParent()
								&& "Check that the the replacement is not erased");
				assert(OpVasI->getParent()->getParent() == &F);
			}
		}
		verifyUsesList(F);
		verifyAfterUpdate("replaceMergedInstructions - createSlice", partI);
#endif
		if (repl != partI) {
			replaceInstUsesWith(*partI, repl);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			verifyUsesList(F);
			verifyAfterUpdate(
					"replaceMergedInstructions - partI replaceAllUsesWith",
					partI);
#endif
		}
		offset += w;
		Worklist.addValue(partI); // add for later DCE
	}
	if (!res->hasName()) {
		auto name = resolveNameForMergedInstructions<ParallelInstVecItemNameGetter>(parallelInstrOnSameVec);
		if (!name.empty()) {
			res->setName(name);
		}
	}
	Worklist.addValue(res);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	verifyUsesList(F);
	verifyAfterUpdate("replaceMergedInstructions", &*Builder.GetInsertPoint());
#endif
}

bool SlicesMergeCombiner::collectParallelInstructionOnSameVectorFindFollowingInstr(
		ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> &extraCheck, bool commutative,
		llvm::Value *op0BitVec, uint64_t op0Offset, uint64_t op0Width,
		size_t op0Index, llvm::Value *op1BitVec, uint64_t op1Offset,
		uint64_t op1Width, size_t op1Index, Instruction *op0Suc,
		bool requireWidthToMatch,
		SlicesMergeCombiner::SliceDict::iterator op1SucSlices) {
	assert(!I.use_empty());
	if (op1BitVec->use_empty())
		return false; // this will be removed later
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
			auto *op0SucUserI = dyn_cast<Instruction>(op0SucUser);
			if (!op0SucUserI)
				continue;
			if (op0SucUserI->getOpcode() != I.getOpcode())
				continue;
			if (op0SucUserI->getParent() != I.getParent())
				continue;
			if (op0SucUserI->use_empty())
				continue;
			if (!extraCheck(*op0SucUserI))
				continue;

			if (isa<Constant>(op1BitVec)) {
				auto op1opValue = op0SucUserI->getOperand(
						commutated ? op0Index : op1Index);
				if (isa<Constant>(op1opValue)) {
					parallelInstrOnSameVec.insertSorted(op0SucUserI,
							commutated);
					size_t w1 = op1opValue->getType()->getIntegerBitWidth();
					// find instruction on successor slices
					// [fixme] the right operand constraint for same vector does not apply
					collectParallelInstructionOnSameVector(
							parallelInstrOnSameVec, I, extraCheck, commutative,
							op0BitVec, op0Offset + w0, op0Width, op0Index,
							op1BitVec, op1Offset + w1, op1Width, op1Index);
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
						if (parallelInstrOnSameVec.canInsert(op0SucUserI)) {
							parallelInstrOnSameVec.insertSorted(op0SucUserI,
									commutated);
							// find instruction on successor slices
							// [fixme] the right operand constraint for same vector does not apply
							collectParallelInstructionOnSameVector(
									parallelInstrOnSameVec, I, extraCheck,
									commutative, op0BitVec, op0Offset + w0,
									op0Width, op0Index, op1BitVec,
									op1Offset + w1, op1Width, op1Index);
							return true;
						}
					}
				}

			}
		}
	}
	return false;
}

bool collectParallelInstructionOnSameVectorForConstSelect(
		ParallelInstVec &parallelInstrOnSameVec, const llvm::SelectInst &I,
		std::function<bool(llvm::Instruction&)> &extraCheck) {
	auto *Cond = I.getCondition();
	bool otherFound = false;
	for (const User *user : Cond->users()) {
		if (user->use_empty())
			continue; // this will be removed later
		if (const SelectInst *OtherI = dyn_cast<SelectInst>(user)) {
			if (OtherI != &I && OtherI->getParent() == I.getParent()
					&& OtherI->getCondition() == Cond
					&& isa<Constant>(OtherI->getTrueValue())
					&& isa<Constant>(OtherI->getFalseValue())
					&& extraCheck(*const_cast<SelectInst*>(OtherI))) {
				parallelInstrOnSameVec.insertSorted(
						const_cast<SelectInst*>(OtherI), false);
				otherFound = true;
			}
		}
	}
	return otherFound;
}

bool collectParallelInstructionOnSameVectorForConstPhi(
		ParallelInstVec &parallelInstrOnSameVec, const llvm::PHINode &I,
		std::function<bool(llvm::Instruction&)> &extraCheck) {
	bool otherFound = false;
	for (const PHINode &OtherI : I.getParent()->phis()) {
		if (OtherI.use_empty())
			continue; // this will be removed later
		if (&OtherI != &I && all_of(OtherI.incoming_values(), [](const Use &u) {
			return isa<Constant>(u.get());
		}) && extraCheck(const_cast<PHINode&>(OtherI))) {
			parallelInstrOnSameVec.insertSorted(&const_cast<PHINode&>(OtherI),
					false);
			otherFound = true;
		}
	}
	return otherFound;
}

bool SlicesMergeCombiner::collectParallelInstructionOnSameVector(
		ParallelInstVec &parallelInstrOnSameVec, const llvm::Instruction &I,
		std::function<bool(llvm::Instruction&)> &extraCheck, bool commutative,
		llvm::Value *op0BitVec, uint64_t op0Offset, uint64_t op0Width,
		size_t op0Index, llvm::Value *op1BitVec, uint64_t op1Offset,
		uint64_t op1Width, size_t op1Index) {
	assert(op0Index != op1Index);
	auto op0asC = dyn_cast<Constant>(op0BitVec);
	auto op0SucSlices = slices.end();
	if (!op0asC) {
		op0SucSlices = slices.find( { op0BitVec, op0Offset + op0Width });
		if (op0BitVec->getType()->getIntegerBitWidth()
				== op0Offset + op0Width) {
			assert(
					op0SucSlices == slices.end()
							&& "This is end of bit vector there should not be any successor slice");
		}
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
	if (op0asC && op1asC) {
		// search for select/phi with constant value operands by searching of the condition
		// * push them into parallelInstrOnSameVec in program order
		if (const SelectInst *SI = dyn_cast<SelectInst>(&I)) {
			return collectParallelInstructionOnSameVectorForConstSelect(
					parallelInstrOnSameVec, *SI, extraCheck);
		} else if (const PHINode *PHI = dyn_cast<PHINode>(&I)) {
			return collectParallelInstructionOnSameVectorForConstPhi(
					parallelInstrOnSameVec, *PHI, extraCheck);
		}
		return false;
		//else if (auto * BI = dyn_cast<BinaryOperator>(&I)) {
		//
		//	//auto &DL = I.getParent()->getParent()->getParent()->getDataLayout();
		//	//Constant* res = ConstantFoldBinaryOpOperands(BI->getOpcode(), op0asC, op1asC, DL);
		//	//assert(res);
		//	//IReplacement = res;
		//	//return false;
		//}
		//I.dump();
		//llvm_unreachable(
		//		"If both are constants this instruction should have already been evaluated");
	}

	for (bool requireWidthToMatch : { true, false }) {
		if (op0asC) {
			assert(op1SucSlices != slices.end());
			// first operand is constant - use slices of second to search for matching instructions
			for (Instruction *op1Suc : op1SucSlices->second) {
				if (collectParallelInstructionOnSameVectorFindFollowingInstr(
						parallelInstrOnSameVec, I, extraCheck,
						commutative, op1BitVec, op1Offset, op1Width, op1Index,
						op0BitVec, op0Offset, op0Width, op0Index, op1Suc,
						requireWidthToMatch, op0SucSlices))
					return true;
			}
		} else {
			assert(op0SucSlices != slices.end());
			for (Instruction *op0Suc : op0SucSlices->second) {
				assert(
						slices.find( { op0BitVec, op0Offset + op0Width })
								!= slices.end());
				if (collectParallelInstructionOnSameVectorFindFollowingInstr(
						parallelInstrOnSameVec, I, extraCheck,
						commutative, op0BitVec, op0Offset, op0Width, op0Index,
						op1BitVec, op1Offset, op1Width, op1Index, op0Suc,
						requireWidthToMatch, op1SucSlices))
					return true;
			}
		}
	}
	return false;
}

std::pair<bool, llvm::Value*> SlicesMergeCombiner::ConcatMemberVector_resolveAndReduce(
		ConcatMemberVector &cmv) {
	bool modified = false;
	auto *res = cmv.resolveValue(Builder, nullptr, &*Builder.GetInsertPoint());
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assertSlicesConsistency();
	Instruction *I = llvm::dyn_cast<Instruction>(cmv.members[0].value);
	if (I) {
		verifyAfterUpdate("ConcatMemberVector_resolveAndReduce", I);
	}
#endif
	Worklist.addValue(res);
	return {modified, res};
}

bool condensateInstructionGroup(BasicBlock &ParentBB,
		ParallelInstVec &parallelInstrOnSameVec, Instruction *&InsertPoint) {
	// try to sink other instructions between parts behind last part
	// try to hoist other instructions between parts before first part
	//errs() << "condensateInstructionGroup:\n";
	std::set<Instruction*> extractedInstructions;
	SetVector<Instruction*> unhoistableInstructions;
	BasicBlock *ParentBlock = nullptr;
	for (const auto &I2 : parallelInstrOnSameVec.iterUnique()) {
		extractedInstructions.insert(I2.I);
		if (ParentBlock) {
			assert(
					ParentBlock == I2.I->getParent()
							&& "Each instruction must be in the same block"
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
		// try to hoist instruction between extractedInstructions, if it fails add it to unhoistableInstructions
		if (extractedInstructions.find(&I2) != extractedInstructions.end()) {
			++seenParInstrCnt;
			if (!isa<PHINode>(I2)
					&& any_of(I2.operand_values(),
							transitivelyDependsOnExtractedParInstr)) {
				// check if any instruction has any previous instruction as a operand
				return false;
			}
			if (firstParInstr == nullptr) {
				firstParInstr = &I2;
				lastParInstr = &I2;
			} else {
				lastParInstr = &I2;
				if (seenParInstrCnt == uniqueInstrCnt)
					break; // end of extracted instruction sequence
			}
		} else if (firstParInstr) {
			// I2.dump();
			// currently in section of instruction where only sequence of parallelInstrOnSameVec should be
			// and this instruction I2 is not going to be extracted
			if (any_of(I2.operand_values(),
					transitivelyDependsOnExtractedParInstr)) {
				unhoistableInstructions.insert(&I2);
			} else {
				// hoist
				assert(&I2 != firstParInstr);
				I2.moveBefore(firstParInstr);
			}
		}
	}
	InsertPoint = lastParInstr->getNextNode();

	if (!unhoistableInstructions.empty()) {
		// try to sink instructions which can not be hoisted
		for (Instruction *I2 : reverse(unhoistableInstructions)) {
			// iterating reversed because we need first move dependent instructions to not break use-def
			if (any_of(I2->users(),
					[&extractedInstructions](User *U) {
						if (auto UI = dyn_cast<Instruction>(U))
							return extractedInstructions.find(UI)
									!= extractedInstructions.end();
						return false;
					})) {
				return false; // can not sink
			} else {
				if (lastParInstr->getNextNode() == InsertPoint) {
					// if insert point was just behind condensated instructions, set it to I2
					// because it will move behind it
					InsertPoint = I2;
				}
				I2->moveAfter(lastParInstr);
			}
		}
	}
	//if (!isa<PHINode>(parallelInstrOnSameVec.begin()->I)) {
	//	// check if any instruction has any previous instruction as a operand
	//	for (auto I = parallelInstrOnSameVec.begin();
	//			I != parallelInstrOnSameVec.end(); ++I) {
	//		if (any_of(I->I->operand_values(),
	//				[&parallelInstrOnSameVec, I](Value *op) {
	//					return any_of(make_range(parallelInstrOnSameVec.begin(), I),
	//							[op](const ParallelInstVecItem &prevM) {
	//								return prevM.I == op;
	//							});
	//				})) {
	//			return false;
	//		}
	//	}
	//}

	return true;
}

bool SlicesMergeCombiner::extractWiderOperandsFromParallelInstructions(
		ParallelInstVec &parallelInstrOnSameVec, BasicBlock &ParentBlock,
		size_t op0Index, size_t op1Index, Value *&widerOp0, Value *&widerOp1,
		bool &modified) {
	assert(
			parallelInstrOnSameVec.uniqueSize() > 1
					&& "Otherwise this is useless and it should not be called");
	//errs() << "extractWiderOperandsFromParallelInstructions:\n";
	//for (auto &I : parallelInstrOnSameVec) {
	//	errs() << "    " << *I.I << "\n";
	//}
	// parallel instructions were discovered
	{
		// move unrelated instructions between extracted instruction up or down
		Instruction *IP = &*Builder.GetInsertPoint();
		// Instruction *OrigIP = IP;
		if (!condensateInstructionGroup(ParentBlock, parallelInstrOnSameVec,
				IP)) {
			Builder.SetInsertPoint(IP);
			// errs() << "extractWiderOperandsFromParallelInstructions finish-fail:\n";
			// errs() << "OrigIP: " << *OrigIP << "\n";
			// errs() << "IP: " << *IP << "\n";
			//
			// for (auto &I : parallelInstrOnSameVec) {
			// 	errs() << "    " << *I.I << "\n";
			// }
			return false; // there is something non removable between instructions
		}
		// :note: if any instruction was sinked the insert point is the most early sinked instruction
		Builder.SetInsertPoint(IP);
	}
	// construct wider operands from parallel instruction operands
	ConcatMemberVector _widerOp0;
	ConcatMemberVector _widerOp1;
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
	// :note: construct concatenations before InsertPoint, then it is possible to construct
	// merged instruction
	bool _modified;
	//errs() << "before widerOp0\n";
	std::tie(_modified, widerOp0) = ConcatMemberVector_resolveAndReduce(
			_widerOp0);
	// errs() << "after widerOp0 " << *widerOp0 << "\n";
	// Builder.GetInsertBlock()->dump();
	// Builder.GetInsertPoint()->dump();
	modified |= _modified;
	//errs() << "before widerOp1\n";
	std::tie(_modified, widerOp1) = ConcatMemberVector_resolveAndReduce(
			_widerOp1);
	//errs() << "after widerOp1 " << *widerOp1 << "\n";
	//Builder.GetInsertBlock()->dump();
	//Builder.GetInsertPoint()->dump();
	modified |= _modified;
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assertSlicesConsistency();
#endif
	// errs() << "extractWiderOperandsFromParallelInstructions finish:\n";
	// for (auto &I : parallelInstrOnSameVec) {
	// 	errs() << "    " << *I.I << "\n";
	// }
	return true;
}

std::tuple<bool, Value*, Value*> SlicesMergeCombiner::mergeConsequentSlicesExtractWiderOperads(
		ParallelInstVec &parallelInstrOnSameVec, Instruction &I,
		std::function<bool(llvm::Instruction&)> extraCheck, bool commutative,
		size_t op0Index, size_t op1Index) {
	assert(parallelInstrOnSameVec.size() == 0 && "Intended for output");
	assert(!I.use_empty());
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
	}
	parallelInstrOnSameVec.insertSorted(&I, false);
	auto op0width = op0->getType()->getIntegerBitWidth();
	auto op1width = op1->getType()->getIntegerBitWidth();

	if (collectParallelInstructionOnSameVector(
			parallelInstrOnSameVec, I, extraCheck, commutative, op0BitVec,
			op0Offset, op0width, op0Index, op1BitVec, op1Offset, op1width,
			op1Index)) {
		//auto *lastMemberI =
		//	const_cast<Instruction*>(parallelInstrOnSameVec.getInstructionClosesToBlockEnd());
		//assert(lastMemberI);
		//builder.SetInsertPoint(lastMemberI->getNextNode());
		// parallel instructions were discovered
		Builder.SetInsertPoint(&I);
		if (!extractWiderOperandsFromParallelInstructions(
				parallelInstrOnSameVec,  *I.getParent(),
				op0Index, op1Index, widerOp0, widerOp1, modified)) {
			// can not extract because there is something non movable between instructions
			return {false, nullptr, nullptr};
		}
		modified = true;
	}
	return {modified, widerOp0, widerOp1};
}

}
