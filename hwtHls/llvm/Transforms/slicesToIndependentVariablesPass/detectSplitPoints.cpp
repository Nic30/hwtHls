#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/detectSplitPoints.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

using namespace llvm;

namespace hwtHls {

const char * metadataNameNoSplit = "hwtHls.slicesToIndependentVariables.noSplit";

inline bool _splitPointsPropagateUpdate(
		SplitPoints::iterator &_splitPoints,
		bool updated, uint64_t bitNo) {
	if (!updated) {
		if (_splitPoints->second.find(bitNo) == _splitPoints->second.end()) {
			_splitPoints->second.insert(bitNo);
			updated = true;
		}
	}
	return updated;
}

void splitPointPropagate(
		SplitPoints &result,
		llvm::Instruction &I, uint64_t bitNo, bool forcePropagation,
		int operandNo, llvm::Instruction *user);

void splitPointPropagate(SplitPoints &result,
		User *U, uint64_t bitNo, bool forcePropagation, int operandNo,
		Instruction *user) {
	if (Instruction *I = dyn_cast<Instruction>(U)) {
		splitPointPropagate(result, *I, bitNo, forcePropagation, operandNo,
				user);
	}
}

bool splitPointPropagateBitRangeGet(Instruction &I, int operandNo, bool updated,
		SplitPoints::iterator &_splitPoints,
		uint64_t bitNo, uint64_t &resultBitNo, bool forcePropagation,
		const hwtHls::OffsetWidthValue &v,
		std::map<Instruction*, std::set<uint64_t> > &result) {
	if (operandNo == -1) {
		// propagation from result to src
		updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
		if (updated || forcePropagation) {
			uint64_t srcBitNo = bitNo + v.offset;
			if (srcBitNo != 0
					&& srcBitNo != v.value->getType()->getIntegerBitWidth()) {
				// propagate lower split point on src operand
				if (auto *I2 = dyn_cast<Instruction>(v.value)) {
					splitPointPropagate(result, *I2, srcBitNo, false, -1, &I);
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
bool splitPointPropagateBitConcatOperand(Instruction &I, const Use &O,
		int operandNo, bool &updated,
		SplitPoints::iterator &_splitPoints,
		uint64_t bitNo, uint64_t &resultBitNo,
		std::map<Instruction*, std::set<uint64_t> > &result, size_t &offset) {
	uint64_t oWidth = O.get()->getType()->getIntegerBitWidth();
	if (operandNo == -1) {
		// find affected operand and propagate to it
		if (bitNo == offset || bitNo == offset + oWidth) {
			// bitNo just hit the boundary we do not need to propagate because split is already there
			return true;
		} else if (bitNo > offset && bitNo < offset + oWidth) {
			// bitNo generated a split point in operand
			if (auto *I2 = dyn_cast<Instruction>(O.get())) {
				splitPointPropagate(result, *I2, bitNo - offset, false, -1, &I);
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
		SplitPoints::iterator & _splitPoints, uint64_t bitNo, bool forcePropagation,
		int operandNo, llvm::BinaryOperator *BO,
		std::map<Instruction*, std::set<uint64_t> > &result) {
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
						splitPointPropagate(result, *I2, bitNo, false, -1, BO);
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
				"Shifts should be converted to concatenations before running this pass");
		break;
	}
	default:
		break;
	}
	return updated;
}

bool splitPointPropagate_SelectInst(bool updated,
		SplitPoints::iterator & _splitPoints, uint64_t bitNo, bool forcePropagation,
		int operandNo, llvm::SelectInst *SI,
		std::map<Instruction*, std::set<uint64_t> > &result) {
	updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
	if (updated || forcePropagation) {
		if (operandNo == -1) {
			for (Value *O : std::vector<Value*>(
					{ SI->getTrueValue(), SI->getFalseValue() })) {
				// propagate to values
				if (auto *I2 = dyn_cast<Instruction>(O)) {
					splitPointPropagate(result, *I2, bitNo, false, -1, SI);
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
					splitPointPropagate(result, *I2, bitNo, false, -1, SI);
				}
				break;
			case 2:
				// if false value changed
				if (auto *I2 = dyn_cast<Instruction>(SI->getTrueValue())) {
					splitPointPropagate(result, *I2, bitNo, false, -1, SI);
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
		SplitPoints::iterator & _splitPoints, uint64_t bitNo, bool forcePropagation,
		llvm::CallInst *C, uint64_t &resultBitNo,
		std::map<Instruction*, std::set<uint64_t> > &result) {
	if (IsBitConcat(C)) {
		bool operandFound = false;
		uint64_t offset = 0;
		for (auto &O : C->args()) {
			operandFound |= splitPointPropagateBitConcatOperand(*C, O, operandNo,
					updated, _splitPoints, bitNo, resultBitNo, result, offset);
		}
		if (operandNo != -1) {
			assert(
					operandFound
							&& "splitPointPropagate operandNo must be operand no of this instruction I");
		}
	} else if (IsBitRangeGet(C)) {
		auto v = BitRangeGetOffsetWidthValue(C);
		updated = splitPointPropagateBitRangeGet(*C, operandNo, updated,
				_splitPoints, bitNo, resultBitNo, forcePropagation, v, result);
	}

	return updated;
}

/*
 * :param operandNo: the index of operand which changed for Instruction I
 * 		-1 marks that the value of I itself was sliced
 * :param user: optional user of this Instruction I, specified if we propagate from user to this I else
 * 		nullptr if we propagate from I to all users
 * */
void splitPointPropagate(SplitPoints &result,
		Instruction &I, uint64_t bitNo, bool forcePropagation, int operandNo,
		Instruction *user) {
	//errs() << "splitPointPropagate:" << I << ", bitNo:" << bitNo << "\n";
	if (operandNo == -1) {
		assert(bitNo > 0 && bitNo < I.getType()->getIntegerBitWidth());
	}
	assert(operandNo == -1 || user == nullptr);
	bool updated = false;
	auto _splitPoints = result.find(&I);
	// process cases where the update is forced or allocation of new set is required
	if (_splitPoints != result.end()) {
		if (operandNo == -1) {
			updated = _splitPointsPropagateUpdate(_splitPoints, false, bitNo);
		}
	} else {
		// the split point set does not exist, we have to create it and initialize it
		if (operandNo == -1) {
			result[&I] = std::set<uint64_t>( { bitNo, });
			updated = true;
		} else {
			result[&I] = std::set<uint64_t>();
		}
		_splitPoints = result.find(&I);
	}
	uint64_t resultBitNo = bitNo;

	if (!I.getMetadata(metadataNameNoSplit)) {
		// process cases specific to each instruction type
		if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
			updated = splitPointPropagate_BinaryOperator(updated, _splitPoints,
					bitNo, forcePropagation, operandNo, BO, result);

		} else if (auto SI = dyn_cast<PHINode>(&I)) {
			updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
			if (updated || forcePropagation) {
				int i = 0;
				for (auto &O : SI->incoming_values()) {
					if (i != operandNo) {
						// avoid propagation back to source of update
						if (auto *I2 = dyn_cast<Instruction>(O.get())) {
							splitPointPropagate(result, *I2, bitNo, false, -1, &I);
						}
					}
					++i;
				}
			}

		} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
			updated = splitPointPropagate_SelectInst(updated, _splitPoints,
					bitNo, forcePropagation, operandNo, SI, result);
		} else if (auto *C = dyn_cast<CallInst>(&I)) {
			updated = splitPointPropagate_CallInst(operandNo, updated,
					_splitPoints, bitNo, forcePropagation, C, resultBitNo,
					result);

		} else if (auto CI = dyn_cast<CastInst>(&I)) {
			switch (CI->getOpcode()) {
			case Instruction::CastOps::Trunc: {
				OffsetWidthValue v = BitRangeGetOffsetWidthValue(
						dyn_cast<TruncInst>(CI));
				updated = splitPointPropagateBitRangeGet(I, operandNo, updated,
						_splitPoints, bitNo, resultBitNo, forcePropagation, v,
						result);
				break;
			}
			case Instruction::CastOps::ZExt:
			case Instruction::CastOps::SExt: {
				auto &o0 = I.getOperandUse(0);
				if (bitNo < o0.get()->getType()->getIntegerBitWidth()) {
					size_t offset = 0;
					splitPointPropagateBitConcatOperand(I, o0, operandNo, updated,
							_splitPoints, bitNo, resultBitNo, result, offset);
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
						u.getOperandNo(), nullptr);
		}
	}
}

/*
 * Collect bit indexes where some slice on each variable is sliced by some bit slice.
 * Bit indexes for each value do specify the boundaries between segments of bit in this Value which are used independently.
 * */
SplitPoints collectSplitPoints(Function &F) {
	SplitPoints result;
	// collect indexes from slices
	for (auto &B : F) {
		for (Instruction &I : B) {
			std::optional<OffsetWidthValue> v;
			if (auto *Call = dyn_cast<CallInst>(&I)) {
				if (IsBitRangeGet(Call)) {
					v = BitRangeGetOffsetWidthValue(Call);
				}
			} else if (isa<CastInst>(&I)) {
				if (auto *Trunc = dyn_cast<TruncInst>(&I))
					v = BitRangeGetOffsetWidthValue(Trunc);
				else if (isa<ZExtInst>(&I)) {
					// mark place where zeros start as splitpoint of self
					v = OffsetWidthValue();
					auto o0 = I.getOperand(0);
					v.value().width = o0->getType()->getIntegerBitWidth();
					v.value().offset = 0;
					v.value().value = &I;
				} else if (isa<SExtInst>(&I)) {
					// mark all bits in extension as split points of self
					auto o0 = I.getOperand(0);
					size_t o0Width = o0->getType()->getIntegerBitWidth();

					auto splitPoints = result.find(&I);
					if (splitPoints == result.end()) {
						result[&I] = std::set<uint64_t>();
						splitPoints = result.find(&I);
					}
					size_t resWidth = I.getType()->getIntegerBitWidth();
					assert(resWidth >= 2);
					// add split point on every position where MSB is replicated
					for (size_t i = o0Width - 1; i < resWidth - 1; ++i) {
						splitPoints->second.insert(i);
					}
					if (auto *I2 = dyn_cast<Instruction>(o0)) {
						// handle extract of msb from operand 0
						v = OffsetWidthValue();
						v.value().width = 1;
						v.value().offset = o0Width - 1 - 1; // msb bit is sliced from rest of the o0
						v.value().value = I2;
					}
				}
			}
			if (v.has_value()) {
				auto _v = v.value();
				if (auto *I2 = dyn_cast<Instruction>(_v.value)) {
					auto splitPoints = result.find(I2);
					if (splitPoints == result.end()) {
						result[I2] = std::set<uint64_t>();
						splitPoints = result.find(I2);
					}
					// add split points, but exclude boundary values
					assert(_v.width > 0);
					if (_v.offset != 0) {
						splitPoints->second.insert(_v.offset);
					}
					if (_v.offset + _v.width
							!= _v.value->getType()->getIntegerBitWidth()) {
						splitPoints->second.insert(_v.offset + _v.width);
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
			if (splitPoints != result.end()) {
				std::set<uint64_t> pointsCopy = splitPoints->second;
				for (uint64_t bitNo : pointsCopy) {
					splitPointPropagate(result, I, bitNo, true, -1, nullptr);
				}
			}
		}
	}
	return result;
}
}
