#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesBinOp.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlicesSelect.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>


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
	}
	return {nullptr, 0};
}

bool mergeConsequentSlices(Instruction &I, DceWorklist::SliceDict &slices,
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce) {
	/*
	 * Merge instructions which are parallel to instruction I and are performed on a consequent slice of same bit vector
	 * */
	bool modified = false;

	if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
		modified = mergeConsequentSlicesBinOp(*BO, slices, createSlice, dce);
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
		modified = mergeConsequentSlicesSelect(*SI, slices, createSlice, dce);
	}
	return modified;
}

void replaceMergedInstructions(const ParallelInstVec &parallelInstrOnSameVec,
		const CreateBitRangeGetFn &createSlice, IRBuilder<> &builder,
		Value *res, DceWorklist &dce, Instruction &I) {
	uint64_t offset = 0;
	for (const auto &_partI : parallelInstrOnSameVec) {
		Instruction *partI = _partI.second;
		auto w = partI->getType()->getIntegerBitWidth();
		partI->replaceAllUsesWith(createSlice(&builder, res, offset, w));
		offset += w;
		dce.insert(*partI);
	}
	I.replaceAllUsesWith(res);
	dce.insert(I);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto &F = *I.getParent()->getParent();
	auto &M = *F.getParent();
	if (verifyModule(M)) {
		F.dump();
		I.dump();
		res->dump();
		throw std::runtime_error("replacing broken");
	}
#endif
}

const Instruction* getInstructionClosesToBlockEnd(const ParallelInstVec &vec) {
	const Instruction *res = nullptr;
	for (auto &I0 : vec) {
		for (auto I1 = I0.second->getIterator();; --I1) {
			if (res == nullptr || &*I1 == res) {
				res = I0.second; // I0 is later in block because we just see res when walking from I0 to begin of the block
			}
			if (I1 == I0.second->getParent()->begin())
				break;
		}
	}
	return res;
}

bool anyOfInstructionsIsUsed(const ParallelInstVec &vec,
		BasicBlock::const_iterator begin, BasicBlock::const_iterator end,
		bool checkAlsoEnd) {
	assert(begin->getParent() == end->getParent());
	if (checkAlsoEnd) {
		++end;
	}
	for (BasicBlock::const_iterator it = begin; it != end; ++it) {
		for (auto &o : it->operands()) {
			for (auto &vItem : vec) {
				if (o.get() == vItem.second)
					return true;
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

	auto op0SucSlices = slices.find( { op0BitVec, op0Offset + op0Width });
	if (op0SucSlices == slices.end())
		return false;
	auto op1SucSlices = slices.find( { op1BitVec, op1Offset + op1Width });
	if (op1SucSlices == slices.end())
		return false;

	bool found = false;
	for (size_t i = 0; i < 2; ++i) {
		for (CallInst *op0Suc : op0SucSlices->second) {
			// for every successor slice of the operand 0 we check if there is an instruction of same type
			// on a successor slice of the the operand 1

			// Hypothetical sliced instruction may be applied multiple times with a different operands
			// on this place we are searching only for instructions which have exactly consequent slices as operands.
			// :note: it is not required for next slice to be of same width but those with the same width should be extracted first.
			bool requireWidthToMatch = i == 1;
			auto w0 = op0Suc->getType()->getIntegerBitWidth();
			if (!requireWidthToMatch || w0 == op0Width) {
				for (Use &op0SucUse : op0Suc->uses()) {
					bool commutated = false;
					// check if use is supported operand in parent instruction
					if (op0SucUse.getOperandNo() != op0Index) {
						if (commutative
								&& op0SucUse.getOperandNo() != op1Index) {
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
							// is instruction of same type in same parent block
							for (CallInst *op1Suc : op1SucSlices->second) {
								// search if the instruction has the other operand of successor slice
								if (op1Suc
										!= op0SucUserI->getOperand(
												commutated ?
														op0Index : op1Index))
									continue;

								auto w1 =
										op1Suc->getType()->getIntegerBitWidth();
								if ((requireWidthToMatch && w1 == op1Width)
										|| (!requireWidthToMatch && w1 == w0)) {
									// check if none of instructions parallelInstrOnSameVec are used between found instruction and this
									auto *lastI =
											getInstructionClosesToBlockEnd(
													parallelInstrOnSameVec);
									if (lastI == nullptr
											|| !anyOfInstructionsIsUsed(
													parallelInstrOnSameVec,
													BasicBlock::const_iterator(
															lastI),
													BasicBlock::const_iterator(
															op0SucUserI),
													true)) {
										parallelInstrOnSameVec.push_back( {
												commutated, op0SucUserI });
										// find instruction on successor slices
										// [fixme] the right operand constraint for same vector does not apply
										collectParallelInstructionOnSameVector(
												slices, parallelInstrOnSameVec,
												I, extraCheck, commutative,
												op0BitVec, op0Offset + w0,
												op0Width, op0Index, op1BitVec,
												op1Offset + w1, op1Width,
												op1Index);
										found = true;
										break;
									}
								}
							}
							if (found)
								break;
						}
					}
				}
				if (found)
					break;
			}
		}
		if (found)
			break;
	}
	return found;
}

std::pair<bool, llvm::Value*> ConcatMemberVector_resolveAndReduce(
		const CreateBitRangeGetFn &createSlice, DceWorklist &dce,
		IRBuilder<> &builder, ConcatMemberVector &cmv) {
	bool modified = false;
	auto *res = cmv.resolveValue(&*builder.GetInsertPoint());
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	Instruction &I = *llvm::dyn_cast<Instruction>(cmv.members[0].value);
	auto &F = *I.getParent()->getParent();
	auto &M = *F.getParent();
	if (verifyModule(M)) {
		F.dump();
		I.dump();
		res->dump();
		throw std::runtime_error("widerOp broken");
	}
#endif
	if (auto *CallI = dyn_cast<CallInst>(res)) {
		if (IsBitConcat(CallI)) {
			modified |= rewriteConcat(CallI, createSlice, dce, &res);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			if (verifyModule(M)) {
				F.dump();
				I.dump();
				CallI->dump();
				throw std::runtime_error("widerOp 1 broken");
			}
#endif
		}
	}
	return {modified, res};
}

std::tuple<bool, Value*, Value*> mergeConsequentSlicesExtractWiderOperads(
		DceWorklist::SliceDict &slices, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce, IRBuilder<> &builder,
		ParallelInstVec &parallelInstrOnSameVec, Instruction &I,
		std::function<bool(llvm::Instruction&)> extraCheck, bool commutative,
		size_t op0Index, size_t op1Index) {
	assert(parallelInstrOnSameVec.size() == 0 && "Intended for output");
	bool modified = false;
	Value *widerOp0 = nullptr;
	Value *widerOp1 = nullptr;
	Value *op0 = I.getOperand(op0Index);
	Value *op1 = I.getOperand(op1Index);
	auto *op0asC = dyn_cast<Constant>(op0);
	auto *op1asC = dyn_cast<Constant>(op1);
	Value *op0BitVec, *op1BitVec;
	uint64_t op0Offset, op1Offset;

	if (op0asC && op1asC) {
		llvm_unreachable("Should be already evaluated");
	}
	std::tie(op0BitVec, op0Offset) = getSliceOffset(op0);
	std::tie(op1BitVec, op1Offset) = getSliceOffset(op1);

	if (!op0asC && op1asC) {
		// not implemented, can possibly merge non-const OP const
	} else if (op0asC && !op1asC) {
		// not implemented, can possibly merge const OP non-const
	} else {
		// !op0asC && !op1asC
		if (!op0BitVec || !op1BitVec)
			return {false, nullptr, nullptr};

		parallelInstrOnSameVec.push_back( { false, &I });
		auto op0width = op0->getType()->getIntegerBitWidth();
		auto op1width = op1->getType()->getIntegerBitWidth();
		if (collectParallelInstructionOnSameVector(slices,
				parallelInstrOnSameVec, I, extraCheck, commutative, op0BitVec,
				op0Offset, op0width, op0Index, op1BitVec, op1Offset, op1width,
				op1Index)) {
			// parallel instructions were discovered, construct wider operands from parallel instruction operands
			auto *lastMemberI =
					const_cast<Instruction*>(getInstructionClosesToBlockEnd(
							parallelInstrOnSameVec));
			builder.SetInsertPoint(lastMemberI);
			ConcatMemberVector _widerOp0(builder, nullptr);
			ConcatMemberVector _widerOp1(builder, nullptr);
			for (auto partI : parallelInstrOnSameVec) {
				// [todo] commutativity
				auto o0 = OffsetWidthValue::fromValue(
						partI.second->getOperand(op0Index));
				auto o1 = OffsetWidthValue::fromValue(
						partI.second->getOperand(op1Index));
				if (partI.first) {
					std::swap(o0, o1);
				}
				_widerOp0.push_back(o0);
				_widerOp1.push_back(o1);
			}
			assert(_widerOp0.width() == _widerOp1.width());
			bool _modified;
			std::tie(_modified, widerOp0) = ConcatMemberVector_resolveAndReduce(
					createSlice, dce, builder, _widerOp0);
			modified |= _modified;
			std::tie(_modified, widerOp1) = ConcatMemberVector_resolveAndReduce(
					createSlice, dce, builder, _widerOp1);
			modified |= _modified;
			modified = true;
			//errs() << "after " << *I.getParent() << "\n";
			//errs() << "new:" << *res << "\n";
			//errs() << "replaced:\n";
			//for (auto partI : parallelInstrOnSameVec) {
			//	errs() << *partI << "\n";
			//}
			//throw runtime_error("[todo] debug err");
		}
	}
	return {modified, widerOp0, widerOp1};
}

}
