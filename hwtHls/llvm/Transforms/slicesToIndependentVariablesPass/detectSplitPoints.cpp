#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/detectSplitPoints.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

using namespace llvm;

namespace hwtHls {

using SplitPointSet = std::set<uint64_t>;

SplitPointSet & splitPointsGetAndInit(SplitPoints &result, Instruction &I) {
	SplitPointSet * splitPoints;
	auto _splitPoints = result.find(&I);
	if (_splitPoints == result.end()) {
		auto tmp = std::make_unique<std::set<uint64_t>>();
		splitPoints = tmp.get();
		result[&I] = std::move(tmp);
	} else {
		splitPoints = _splitPoints->second.get();
	}
	return *splitPoints;
}

inline bool _splitPointsPropagateUpdate(SplitPointSet& _splitPoints,
		bool updated, uint64_t bitNo) {
	if (!updated) {
		if (bitNo != 0 && _splitPoints.find(bitNo) == _splitPoints.end()) {
			_splitPoints.insert(bitNo);
			updated = true;
		}
	}
	return updated;
}

void splitPointPropagate(SplitPoints &result, llvm::Instruction &I,
		uint64_t bitNo, bool forcePropagation, int operandNo,
		llvm::Instruction *user, InstrSet &noSplitInstrs);

void splitPointPropagate(SplitPoints &result, User *U, uint64_t bitNo,
		bool forcePropagation, int operandNo, Instruction *user,
		InstrSet &noSplitInstrs) {
	if (Instruction *I = dyn_cast<Instruction>(U)) {
		splitPointPropagate(result, *I, bitNo, forcePropagation, operandNo,
				user, noSplitInstrs);
	}
}

bool splitPointPropagate_BitRangeGet(Instruction &I, int operandNo,
		bool updated, SplitPointSet& _splitPoints, uint64_t bitNo,
		uint64_t &resultBitNo, bool forcePropagation,
		const hwtHls::OffsetWidthValue &v, SplitPoints &result,
		InstrSet &noSplitInstrs) {
	if (operandNo == -1) {
		// propagation from result to src
		updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
		if (updated || forcePropagation) {
			uint64_t srcBitNo = bitNo + v.offset;
			if (srcBitNo != 0
					&& srcBitNo != v.value->getType()->getIntegerBitWidth()) {
				// propagate lower split point on src operand
				if (auto *I2 = dyn_cast<Instruction>(v.value)) {
					splitPointPropagate(result, *I2, srcBitNo, false, -1, &I,
							noSplitInstrs);
				}
			}
		}
	} else {
		// propagation from src to result
		if (bitNo > v.offset && bitNo < v.width + v.offset - 1) {
			// skip if bitNo is under or above bits selected by slice
			resultBitNo = bitNo - v.offset;
			updated = _splitPointsPropagateUpdate(_splitPoints, false,
					resultBitNo);
		}
		// no need to update operands as the only operand was causing this update and is already updated
	}
	return updated;
}

/*
 * :return: true if operand O matches the requested range and the search for operand may end
 * */
bool splitPointPropagate_BitConcatOperand(Instruction &I, const Use &O,
		int operandNo, bool &updated, SplitPointSet &_splitPoints,
		uint64_t bitNo, uint64_t &resultBitNo, SplitPoints &result,
		size_t &offset, InstrSet &noSplitInstrs) {
	uint64_t oWidth = O.get()->getType()->getIntegerBitWidth();
	if (operandNo == -1) {
		// find affected operand and propagate to it
		if (bitNo == offset || bitNo == offset + oWidth) {
			// bitNo just hit the boundary we do not need to propagate because split is already there
			return true;
		} else if (bitNo > offset && bitNo < offset + oWidth) {
			// bitNo generated a split point in operand
			if (auto *I2 = dyn_cast<Instruction>(O.get())) {
				splitPointPropagate(result, *I2, bitNo - offset, false, -1, &I,
						noSplitInstrs);
			}
			return true;
		}
	} else {
		// find offset of operand in result
		if (O.getOperandNo() == (unsigned) operandNo) {
			assert(bitNo <= oWidth);
			resultBitNo = offset + bitNo;
			updated |= _splitPointsPropagateUpdate(_splitPoints, false,
					resultBitNo);
			return true;
		}
	}
	offset += oWidth;
	return false;
}

bool splitPointPropagate_BinaryOperator(bool updated,
		SplitPointSet &_splitPoints, uint64_t bitNo,
		bool forcePropagation, int operandNo, llvm::BinaryOperator *BO,
		SplitPoints &result, InstrSet &noSplitInstrs) {
	switch (BO->getOpcode()) {
	case Instruction::BinaryOps::And:
	case Instruction::BinaryOps::Or:
	case Instruction::BinaryOps::Xor: {
		updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
		if (updated || forcePropagation) {
			// no bitNo translation needed
			int i = 0;
			for (auto &O : BO->operands()) {
				if (i != operandNo) {
					if (auto *I2 = dyn_cast<Instruction>(O.get())) {
						splitPointPropagate(result, *I2, bitNo, false, -1, BO,
								noSplitInstrs);
					}
				}
			}
		}
		break;
	}
	case Instruction::BinaryOps::Shl: // Shift left  (logical)
	case Instruction::BinaryOps::LShr: // Shift right (logical)
	case Instruction::BinaryOps::AShr: // Shift right (arithmetic)
	{
		BO->dump();
		llvm_unreachable(
				"Shifts should be converted to concatenations or have hwtHls.slicesToIndependentVariables.noSplit attribute before running this pass");
		break;
	}
	default:
		break;
	}
	return updated;
}

bool splitPointPropagate_SelectInst(bool updated,
		SplitPointSet &_splitPoints, uint64_t bitNo,
		bool forcePropagation, int operandNo, llvm::SelectInst *SI,
		SplitPoints &result, InstrSet &noSplitInstrs) {
	updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
	if (updated || forcePropagation) {
		if (operandNo == -1) {
			for (Value *O : std::vector<Value*>(
					{ SI->getTrueValue(), SI->getFalseValue() })) {
				// propagate to values
				if (auto *I2 = dyn_cast<Instruction>(O)) {
					splitPointPropagate(result, *I2, bitNo, false, -1, SI,
							noSplitInstrs);
				}
			}
		} else {
			switch (operandNo) {
			case 0:
				// 1b condition, no propagation needed
				break;
			case 1:
				// if true value changed
				if (auto *I2 = dyn_cast<Instruction>(SI->getFalseValue())) {
					splitPointPropagate(result, *I2, bitNo, false, -1, SI,
							noSplitInstrs);
				}
				break;
			case 2:
				// if false value changed
				if (auto *I2 = dyn_cast<Instruction>(SI->getTrueValue())) {
					splitPointPropagate(result, *I2, bitNo, false, -1, SI,
							noSplitInstrs);
				}
				break;
			default:
				SI->dump();
				llvm_unreachable(
						"Select instruction should have 3 operands at most (cond, ifTrue, ifFalse)");
			}
		}
	}
	return updated;
}

bool splitPointPropagate_CallInst(int operandNo, bool updated,
		SplitPointSet& _splitPoints, uint64_t bitNo,
		bool forcePropagation, llvm::CallInst *C, uint64_t &resultBitNo,
		SplitPoints &result, InstrSet &noSplitInstrs) {
	if (IsBitConcat(C)) {
		bool operandFound = false;
		uint64_t offset = 0;
		for (auto &O : C->args()) {
			operandFound |= splitPointPropagate_BitConcatOperand(*C, O,
					operandNo, updated, _splitPoints, bitNo, resultBitNo,
					result, offset, noSplitInstrs);
		}
		if (operandNo != -1) {
			assert(
					operandFound
							&& "splitPointPropagate operandNo must be operand no of this instruction I");
		}
	} else if (IsBitRangeGet(C)) {
		auto v = BitRangeGetOffsetWidthValue(C);
		updated = splitPointPropagate_BitRangeGet(*C, operandNo, updated,
				_splitPoints, bitNo, resultBitNo, forcePropagation, v, result,
				noSplitInstrs);
	}

	return updated;
}

/*
 * :param operandNo: the index of operand which changed for Instruction I
 * 		-1 marks that the value of I itself was sliced
 * :param user: optional user of this Instruction I, specified if we propagate from user to this I else
 * 		nullptr if we propagate from I to all users
 * */
void splitPointPropagate(SplitPoints &result, Instruction &I, uint64_t bitNo,
		bool forcePropagation, int operandNo, Instruction *user,
		InstrSet &noSplitInstrs) {
	//errs() << "splitPointPropagate:" << I << ", bitNo:" << bitNo << "\n";
	if (operandNo == -1) {
		assert(bitNo > 0 && bitNo < I.getType()->getIntegerBitWidth());
	}
	assert(operandNo == -1 || user == nullptr);
	bool updated = false;
	auto _splitPoints = result.find(&I);
	SplitPointSet *  splitPoints;
	// process cases where the update is forced or allocation of new set is required
	if (_splitPoints != result.end()) {
		splitPoints = _splitPoints->second.get();
		if (operandNo == -1) {
			updated = _splitPointsPropagateUpdate(*splitPoints, false, bitNo);
		}
	} else {
		// the split point set does not exist, we have to create it and initialize it
		auto tmp = std::make_unique<SplitPointSet>();
		if (operandNo == -1) {
			assert(bitNo > 0 && bitNo < I.getType()->getIntegerBitWidth());
			tmp->insert(bitNo);
			updated = true;
		}
		splitPoints = tmp.get();
		result[&I] = std::move(tmp);
	}
	uint64_t resultBitNo = bitNo;

	if (noSplitInstrs.find(&I) == noSplitInstrs.end()) {
		// process cases specific to each instruction type
		if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
			updated = splitPointPropagate_BinaryOperator(updated, *splitPoints,
					bitNo, forcePropagation, operandNo, BO, result,
					noSplitInstrs);

		} else if (auto SI = dyn_cast<PHINode>(&I)) {
			updated = _splitPointsPropagateUpdate(*splitPoints, updated, bitNo);
			if (updated || forcePropagation) {
				int i = 0;
				for (auto &O : SI->incoming_values()) {
					if (i != operandNo) {
						// avoid propagation back to source of update
						if (auto *I2 = dyn_cast<Instruction>(O.get())) {
							splitPointPropagate(result, *I2, bitNo, false, -1,
									&I, noSplitInstrs);
						}
					}
					++i;
				}
			}

		} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
			updated = splitPointPropagate_SelectInst(updated, *splitPoints,
					bitNo, forcePropagation, operandNo, SI, result,
					noSplitInstrs);
		} else if (auto *C = dyn_cast<CallInst>(&I)) {
			updated = splitPointPropagate_CallInst(operandNo, updated,
					*splitPoints, bitNo, forcePropagation, C, resultBitNo,
					result, noSplitInstrs);

		} else if (auto CI = dyn_cast<CastInst>(&I)) {
			switch (CI->getOpcode()) {
			case Instruction::CastOps::Trunc: {
				OffsetWidthValue v = BitRangeGetOffsetWidthValue(
						dyn_cast<TruncInst>(CI));
				updated = splitPointPropagate_BitRangeGet(I, operandNo, updated,
						*splitPoints, bitNo, resultBitNo, forcePropagation, v,
						result, noSplitInstrs);
				break;
			}
			case Instruction::CastOps::ZExt:
			case Instruction::CastOps::SExt: {
				auto &o0 = I.getOperandUse(0);
				if (bitNo < o0.get()->getType()->getIntegerBitWidth()) {
					size_t offset = 0;
					splitPointPropagate_BitConcatOperand(I, o0, operandNo,
							updated, *splitPoints, bitNo, resultBitNo, result,
							offset, noSplitInstrs);
				}
				break;
			}
			default:
				break;
			}

		}
	}

	if (updated || forcePropagation) {
		for (auto &u : I.uses()) {
			if (u.getUser() != user)
				splitPointPropagate(result, u.getUser(), resultBitNo, false,
						u.getOperandNo(), nullptr, noSplitInstrs);
		}
	}
}

/*
 * Collect bit indexes where some slice on each variable is sliced by some bit slice.
 * Bit indexes for each value do specify the boundaries between segments of bit in this Value which are used independently.
 * */
SplitPoints collectSplitPoints(Function &F, InstrSet &noSplitInstrs) {
	SplitPoints result;
	// collect indexes from slices
	for (auto &B : F) {
		for (Instruction &I : B) {
			bool hasNoSplit = I.getMetadata(SlicesToIndependentVariablesPass::metadataName_NoSplit);
			if (hasNoSplit) {
				noSplitInstrs.insert(&I);
				//continue;
			}

			std::optional<OffsetWidthValue> v;
			if (auto *Call = dyn_cast<CallInst>(&I)) {
				if (IsBitRangeGet(Call)) {
					v = BitRangeGetOffsetWidthValue(Call);
				}
			} else if (isa<CastInst>(&I)) {
				if (auto *Trunc = dyn_cast<TruncInst>(&I))
					v = BitRangeGetOffsetWidthValue(Trunc);
				else if (isa<ZExtInst>(&I)) {
					if (!hasNoSplit) {
						// mark place where zeros start as splitpoint of self
						v = OffsetWidthValue();
						auto o0 = I.getOperand(0);
						v.value().width = o0->getType()->getIntegerBitWidth();
						v.value().offset = 0;
						v.value().value = &I;
					}
				} else if (isa<SExtInst>(&I)) {
					if (!hasNoSplit) {
						// mark all bits in extension as split points of self
						auto srcOp = I.getOperand(0);
						size_t srcOpWidth = srcOp->getType()->getIntegerBitWidth();

						SplitPointSet & splitPoints = splitPointsGetAndInit(result, I);
						size_t resWidth = I.getType()->getIntegerBitWidth();
						assert(resWidth >= 2);
						// add split point on every position where MSB is replicated
						for (size_t i = srcOpWidth - 1; i < resWidth - 1; ++i) {
							if (i == 0)
								continue;
							splitPoints.insert(i);
						}
						if (auto *I2 = dyn_cast<Instruction>(srcOp)) {
							// handle extract of msb from operand 0
							v = OffsetWidthValue();
							v.value().width = 1;
							v.value().offset = srcOpWidth - 1; // msb bit is sliced from rest of the srcOp
							v.value().value = I2;
						}
					}
				}
			}
			if (v.has_value()) {
				auto _v = v.value();
				if (auto *I2 = dyn_cast<Instruction>(_v.value)) {
					SplitPointSet & splitPoints = splitPointsGetAndInit(result, *I2);
						// add split points, but exclude boundary values
					assert(_v.width > 0);
					if (_v.offset != 0) {
						splitPoints.insert(_v.offset);
					}
					auto srcWidth = _v.value->getType()->getIntegerBitWidth();
					if (_v.offset + _v.width != srcWidth) {
						splitPoints.insert(_v.offset + _v.width);
					}
				}
			}
		}
	}
	// transitively propagate (in both directions)
	for (auto &B : F) {
		for (Instruction &I : B) {
			// we have to propagate in both directions because the propagation may end on non splitable instructions like multiplication etc.
			auto splitPoints = result.find(&I);
			if (splitPoints == result.end())
				continue;
			std::set<uint64_t> pointsCopy = *splitPoints->second;
#ifndef NDEBUG
			for (auto bitNo : pointsCopy) {
				assert(bitNo > 0);
				assert(bitNo < I.getType()->getIntegerBitWidth());
			}
#endif
			for (uint64_t bitNo : pointsCopy) {
				splitPointPropagate(result, I, bitNo, true, -1, nullptr,
						noSplitInstrs);
			}
		}
	}
	return result;
}
}
