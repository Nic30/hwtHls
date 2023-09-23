#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/detectSplitPoints.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>

using namespace llvm;

namespace hwtHls {

inline bool _splitPointsPropagateUpdate(
		std::map<Instruction*, std::set<uint64_t>>::iterator &_splitPoints,
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
		std::map<llvm::Instruction*, std::set<uint64_t>> &result,
		llvm::Instruction &I, uint64_t bitNo, bool forcePropagation,
		int operandNo, llvm::Instruction *user);

void splitPointPropagate(std::map<Instruction*, std::set<uint64_t>> &result,
		User *U, uint64_t bitNo, bool forcePropagation, int operandNo,
		Instruction *user) {
	if (Instruction *I = dyn_cast<Instruction>(U)) {
		splitPointPropagate(result, *I, bitNo, forcePropagation, operandNo,
				user);
	}
}

/*
 * :param operandNo: the index of operand which changed for Instruction I
 * 		-1 marks that the value of I itself was sliced
 * :param user: optional user of this Instruction I, specified if we propagate from user to this I else
 * 		nullptr if we propagate from I to all users
 * */
void splitPointPropagate(std::map<Instruction*, std::set<uint64_t>> &result,
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

	// process cases specific to each instruction type
	if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
		switch (BO->getOpcode()) {
		case Instruction::BinaryOps::And:
		case Instruction::BinaryOps::Or:
		case Instruction::BinaryOps::Xor: {
			updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
			if (updated || forcePropagation) {
				// no bitNo translation needed
				int i = 0;
				for (auto &O : I.operands()) {
					if (i != operandNo) {
						if (auto *I2 = dyn_cast<Instruction>(O.get())) {
							splitPointPropagate(result, *I2, bitNo, false, -1,
									&I);
						}
					}
				}
			}
			break;
		}
		case Instruction::BinaryOps::Shl: // Shift left  (logical)
		case Instruction::BinaryOps::LShr: // Shift right (logical)
		case Instruction::BinaryOps::AShr: { // Shift right (arithmetic)
			llvm_unreachable(
					"Shifts should be converted to concatenations before running this pass");
			break;
		}
		default:
			break;
		}

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
		updated = _splitPointsPropagateUpdate(_splitPoints, updated, bitNo);
		if (updated || forcePropagation) {
			if (operandNo == -1) {
				for (Value *O : std::vector<Value*>(
						{ SI->getTrueValue(), SI->getFalseValue() })) {
					// propagate to values
					if (auto *I2 = dyn_cast<Instruction>(O)) {
						splitPointPropagate(result, *I2, bitNo, false, -1, &I);
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
						splitPointPropagate(result, *I2, bitNo, false, -1, &I);
					}
					break;
				case 2:
					// if false value changed
					if (auto *I2 = dyn_cast<Instruction>(SI->getTrueValue())) {
						splitPointPropagate(result, *I2, bitNo, false, -1, &I);
					}
					break;
				default:
					llvm_unreachable(
							"Select instruction should have 3 operands at most (cond, ifTrue, ifFalse)");
				}
			}
		}

	} else if (auto *C = dyn_cast<CallInst>(&I)) {
		if (IsBitConcat(C)) {
			if (operandNo == -1) {
				// find affected operand and propagate to it
				uint64_t offset = 0;
				for (auto &O : C->args()) {
					uint64_t oWidth = O.get()->getType()->getIntegerBitWidth();
					if (bitNo == offset || bitNo == offset + oWidth) {
						// bitNo just hit the boundary we do not need to propagate because split is already there
						break;
					} else if (bitNo > offset && bitNo < offset + oWidth) {
						// bitNo generated a split point in operand
						if (auto *I2 = dyn_cast<Instruction>(O.get())) {
							splitPointPropagate(result, *I2, bitNo - offset,
									false, -1, &I);
						}
						break;
					}
					offset += oWidth;
				}
			} else {
				// find offset of operand in result
				uint64_t offset = 0;
				bool operandFound = false;
				for (auto &O : C->args()) {
					uint64_t oWidth = O.get()->getType()->getIntegerBitWidth();
					if (O.getOperandNo() == (unsigned) operandNo) {
						assert(bitNo <= oWidth);
						resultBitNo = offset + bitNo;
						updated = _splitPointsPropagateUpdate(_splitPoints,
								false, resultBitNo);
						operandFound = true;
						break;
					}
					offset += oWidth;
				}
				assert(operandFound && "splitPointPropagate operandNo must be operand no of this instruction I");
			}
		} else if (IsBitRangeGet(C)) {
			auto v = BitRangeGetOffsetWidthValue(C);
			if (operandNo == -1) {
				// propagation from result to src
				updated = _splitPointsPropagateUpdate(_splitPoints, updated,
						bitNo);
				if (updated || forcePropagation) {
					uint64_t srcBitNo = bitNo + v.offset;
					if (srcBitNo != 0
							&& srcBitNo
									!= v.value->getType()->getIntegerBitWidth()) {
						// propagate lower split point on src operand
						if (auto *I2 = dyn_cast<Instruction>(v.value)) {
							splitPointPropagate(result, *I2, srcBitNo, false,
									-1, &I);
						}
					}
				}

			} else {
				// propagation from src to result
				if (bitNo > v.offset && bitNo < v.width + v.offset - 1) {
					// skip if bitNo is under or above bits selected by slice
					resultBitNo = bitNo - v.offset;
					updated = _splitPointsPropagateUpdate(_splitPoints,
							false, resultBitNo);
				}
				// no need to update operands as the only operand was causing this update and is already updated
			}
		}

	} else if (auto CI = dyn_cast<CastInst>(&I)) {
		switch (CI->getOpcode()) {
		case Instruction::CastOps::Trunc:
		case Instruction::CastOps::ZExt:
		case Instruction::CastOps::SExt:
			llvm_unreachable(
					"Extensions and truncat should be converted to concatenations before running this pass");
		default:
			break;
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
std::map<Instruction*, std::set<uint64_t>> collectSplitPoints(Function &F) {
	std::map<Instruction*, std::set<uint64_t>> result;
	// collect indexes from slices
	for (auto &B : F) {
		for (Instruction &I : B) {
			if (auto *Call = dyn_cast<CallInst>(&I)) {
				if (IsBitRangeGet(Call)) {
					auto v = BitRangeGetOffsetWidthValue(Call);
					if (auto *I2 = dyn_cast<Instruction>(v.value)) {
						auto splitPoints = result.find(I2);
						if (splitPoints == result.end()) {
							result[I2] = std::set<uint64_t>();
							splitPoints = result.find(I2);
						}
						// add split points, but exclude boundary values
						assert(v.offset >= 0);
						assert(v.width > 0);
						if (v.offset != 0) {
							splitPoints->second.insert(v.offset);
						}
						if (v.offset + v.width
								!= v.value->getType()->getIntegerBitWidth()) {
							splitPoints->second.insert(v.offset + v.width);
						}
					}
				}
			}
		}
	}
	/*
	 errs() << "Original split points\n";
	 for (auto &item : result) {
	 errs() << *item.first;
	 errs() << "    ";
	 for (auto p : item.second) {
	 errs() << p << " ";
	 }
	 errs() << "\n";
	 }*/
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
