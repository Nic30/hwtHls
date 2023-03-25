#include "slicesMerge.h"
#include <map>
#include <sstream>

#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Scalar/NewGVN.h>
#include <llvm/IR/Dominators.h>

#include "../../targets/intrinsic/bitrange.h"
#include "../slicesToIndependentVariablesPass/concatMemberVector.h"
#include "rewriteConcat.h"
#include "dceWorklist.h"
#include "rewritePhiShift.h"

using namespace llvm;
using namespace std;

namespace hwtHls {

pair<Value*, uint64_t> getSliceOffset(Value *op0) {
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

/*
 * :param parallelInstrOnSameVec: lowest first vector of instructions on same slice which have slices of the same bit vector as operands
 * 		When searching the same width of slices is prioritized but it is not required.
 * */
bool collectParallelInstructionsOnSameVector(DceWorklist::SliceDict &slices, Value *op0BitVec, uint64_t op0Offset,
		uint64_t op0Width, Value *op1BitVec, uint64_t op1Offset, uint64_t op1Width,
		std::vector<Instruction*> &parallelInstrOnSameVec, const Instruction &I) {

	auto op0SucSlices = slices.find( { op0BitVec, op0Offset + op0Width });
	if (op0SucSlices == slices.end())
		return false;
	auto op1SucSlices = slices.find( { op1BitVec, op1Offset + op1Width });
	if (op1SucSlices == slices.end())
		return false;

	bool found = false;
	for (size_t i = 0; i < 2; ++i) {
		for (CallInst *op0Suc : op0SucSlices->second) {
			// for every successor slice of the operand 0 we check if there is an instruction of same
			// on a successor slice of the the operand 1

			// Hypothetical sliced instruction may be applied multiple times with a different operands
			// on this place we are searching only those instructions which have exactly consequent slices as operands.
			// :note: it is not required for next slice to be of same width but those with the same width should be extracted first.
			bool requireWidthToMatch = i == 1;
			auto w0 = op0Suc->getType()->getIntegerBitWidth();
			if (!requireWidthToMatch || w0 == op0Width) {
				for (auto &op0SucUse : op0Suc->uses()) {
					auto *op0SucUser = op0SucUse.getUser();
					if (auto *op0SucUserI = dyn_cast<Instruction>(op0SucUser)) {
						if (op0SucUserI->getOpcode() == I.getOpcode() && op0SucUserI->getParent() == I.getParent()) {
							// is instruction of same type in same parent
							for (CallInst *op1Suc : op1SucSlices->second) {
								auto w1 = op1Suc->getType()->getIntegerBitWidth();
								if ((!requireWidthToMatch && w1 == w0) || w1 == op1Width) {
									parallelInstrOnSameVec.push_back(op0SucUserI);
									// find instruction on successor slices
									collectParallelInstructionsOnSameVector(slices, op0BitVec, op0Offset + w0, op0Width,
											op1BitVec, op1Offset + w1, op1Width, parallelInstrOnSameVec, I);
									found = true;
									break;
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

bool mergeConsequentSlices(Instruction &I, DceWorklist::SliceDict &slices, const CreateBitRangeGetFn &createSlice,
		DceWorklist &dce) {
	/*
	 * Merge instructions which are parallel to instruction I and are performed on a consequent slice of same bit vector
	 * */
	bool modified = false;

	if (auto *BO = dyn_cast<BinaryOperator>(&I)) {

		Value *op0 = I.getOperand(0);
		Value *op1 = I.getOperand(1);
		auto *op0asC = dyn_cast<Constant>(op0);
		auto *op1asC = dyn_cast<Constant>(op1);
		Value *op0BitVec, *op1BitVec;
		uint64_t op0Offset, op1Offset;

		if (op0asC && op1asC) {
			llvm_unreachable("Should be already evaluated");
		}
		tie(op0BitVec, op0Offset) = getSliceOffset(op0);
		tie(op1BitVec, op1Offset) = getSliceOffset(op1);

		if (!op0asC && op1asC) {
		} else if (op0asC && !op1asC) {
		} else {
			// !op0asC && !op1asC
			if (!op0BitVec || !op1BitVec)
				return false;

			std::vector<Instruction*> parallelInstrOnSameVec = { &I };
			auto op0width = op0->getType()->getIntegerBitWidth();
			auto op1width = op1->getType()->getIntegerBitWidth();
			if (collectParallelInstructionsOnSameVector(slices, op0BitVec, op0Offset, op0width, op1BitVec, op1Offset,
					op1width, parallelInstrOnSameVec, I)) {
				IRBuilder<> builder(&I);
				ConcatMemberVector _widerOp0(builder, nullptr);
				ConcatMemberVector _widerOp1(builder, nullptr);
				for (auto partI : parallelInstrOnSameVec) {
					_widerOp0.push_back(OffsetWidthValue::fromValue(partI->getOperand(0)));
					_widerOp1.push_back(OffsetWidthValue::fromValue(partI->getOperand(1)));
				}
				auto widerOp0 = _widerOp0.resolveValue(&I);
				if (auto *CallI = dyn_cast<CallInst>(widerOp0)) {
					if (IsBitConcat(CallI)) {
						modified |= rewriteConcat(CallI, createSlice, dce);
					}
				}

				auto widerOp1 = _widerOp1.resolveValue(&I);
				if (auto *CallI = dyn_cast<CallInst>(widerOp1)) {
					if (IsBitConcat(CallI)) {
						modified |= rewriteConcat(CallI, createSlice, dce);
					}
				}

				Value *res = nullptr;
				switch (BO->getOpcode()) {
				case Instruction::BinaryOps::And:
					res = builder.CreateAnd(widerOp0, widerOp1);
					break;
				case Instruction::BinaryOps::Or:
					res = builder.CreateOr(widerOp0, widerOp1);
					break;
				case Instruction::BinaryOps::Xor:
					res = builder.CreateXor(widerOp0, widerOp1);
					break;
				default:
					errs() << *BO << "\n";
					llvm_unreachable("Not implemented binary operator");
				}
				uint64_t offset = 0;
				for (auto partI : parallelInstrOnSameVec) {
					auto w = partI->getType()->getIntegerBitWidth();
					partI->replaceAllUsesWith(createSlice(&builder, res, builder.getInt64(offset), w));
					offset += w;
					dce.insert(*partI);
				}
				modified = true;
				I.replaceAllUsesWith(res);
				dce.insert(I);
			}
		}

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
	//} else if (dyn_cast<SelectInst>(I)) {
	//	// translate operands then build a new operand with new operands if required
	//	Value *opCond = I.getOperand(0);
	//	Value *opTrue = I.getOperand(1);
	//	Value *opFalse = I.getOperand(2);
	//	Value *res = nullptr;
	//
	//}
	return modified;
}

DceWorklist::SliceDict findSlices(Function &F) {
	DceWorklist::SliceDict slices;
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *CallI = dyn_cast<CallInst>(&I)) {
				if (IsBitRangeGet(CallI)) {
					auto *_offset = CallI->getArgOperand(1);
					if (auto *offset = dyn_cast<ConstantInt>(_offset)) {
						auto offsetInt = offset->getZExtValue();
						auto *bitVector = CallI->getArgOperand(0);
						auto curSlices = slices.find( { bitVector, offsetInt });
						if (curSlices == slices.end()) {
							slices[ { bitVector, offsetInt }] = { CallI };
						}
					}
				}
			}
		}
	}
	return slices;
}

PreservedAnalyses SlicesMergePass::run(Function &F, FunctionAnalysisManager &AM) {
	// F.dump();
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	bool anyChange = false;
	bool firstRun = true;
	while (true) {
		bool change = false;
		DceWorklist::SliceDict slices = findSlices(F);
		auto createSlice = [&slices](IRBuilder<> *Builder, Value *bitVec, Value *lowBitNo, size_t bitWidth) {
			if (auto lowBitNoConst = dyn_cast<ConstantInt>(lowBitNo)) {
				uint64_t lowBitNoConstInt = lowBitNoConst->getZExtValue();
				std::pair<Value*, uint64_t> key(bitVec, lowBitNoConstInt);
				auto cur = slices.find(key);
				if (cur == slices.end()) {
					auto slice = CreateBitRangeGet(Builder, bitVec, lowBitNo, bitWidth);
					slices[key] = { slice };
					return slice;
				} else {
					for (auto sliceItem : cur->second) {
						if (sliceItem->getType()->getIntegerBitWidth() == bitWidth) {
							return sliceItem;
						}
					}
					auto slice = CreateBitRangeGet(Builder, bitVec, lowBitNo, bitWidth);
					cur->second.push_back(slice);
					return slice;
				}
			}
			return CreateBitRangeGet(Builder, bitVec, lowBitNo, bitWidth);
		};

		for (BasicBlock &BB : F) {
			change |= phiShiftPatternRewrite(BB, createSlice);
		}
		DceWorklist dce(TLI, &slices);
		for (BasicBlock &BB : F) {
			for (auto I = BB.begin(); I != BB.end();) {
				if (dce.tryRemoveIfDead(*I, I)) {
					dce.runToCompletition(I);
					change = true;
					continue;
				}
				//dbgs() << "rewriting" << *I << "\n";

				bool _changed = false;
				if (auto *CallI = dyn_cast<CallInst>(&*I)) {
					if (IsBitConcat(CallI)) {
						_changed = rewriteConcat(CallI, createSlice, dce);
					}
				}

				if (!_changed && !slices.empty()) {
					_changed |= mergeConsequentSlices(*I, slices, createSlice, dce);
				}
				change |= _changed;
				if (_changed) {
					change |= dce.tryRemoveIfDead(*I, I);
					change = dce.runToCompletition(I);
				} else {
					assert(dce.empty() && "If there is something in DCE worklist there must have been some change");
					++I;
				}
			}
		}
		anyChange |= change;
		if (!firstRun && !change) {
			break;
		}
		firstRun = false;
		bool _change = false;
		InstCombinePass ic;
		auto ICres = ic.run(F, AM);
		if (!ICres.areAllPreserved()) {
			_change = true;
		}
		NewGVNPass gnv;
		auto gnvRes = gnv.run(F, AM);
		if (!gnvRes.areAllPreserved()) {
			_change = true;
		}
		anyChange |= _change;
	}
	//}
	//dbgs() << "----------------------------------------- after -------------------------------------\n";
	//F.dump();
	//throw runtime_error("[todo] debug err");
	assert(!verifyModule(*F.getParent()));
	if (anyChange) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}
}
