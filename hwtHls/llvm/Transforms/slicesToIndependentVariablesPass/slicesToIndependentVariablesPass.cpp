#include "slicesToIndependentVariablesPass.h"
#include <map>
#include <set>

#include "../../targets/intrinsic/bitrange.h"
#include "detectSplitPoints.h"
#include "concatMemberVector.h"

using namespace llvm;

namespace hwtHls {

class SlicedValueResolver {
public:

	const std::map<Instruction*, std::set<uint64_t>> &splitPoints;
	IRBuilder<> &builder;
	std::unordered_map<OffsetWidthValue, Value*> commonSubexpressionCache;

	SlicedValueResolver(
			const std::map<Instruction*, std::set<uint64_t>> &splitPoints,
			IRBuilder<> &builder) :
			splitPoints(splitPoints), builder(builder) {
	}

	static bool isInstructionSplitable(Instruction &I) {
		if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
			switch (BO->getOpcode()) {
			case Instruction::BinaryOps::And:
			case Instruction::BinaryOps::Or:
			case Instruction::BinaryOps::Xor:
				return true;
			default:
				break;
			};
		} else if (dyn_cast<PHINode>(&I)) {
			return true;
		} else if (dyn_cast<SelectInst>(&I)) {
			return true;
		} else if (auto *C = dyn_cast<CallInst>(&I)) {
			if (IsBitConcat(C) || IsBitRangeGet(C))
				return true;
		}
		return false;
	}

	void resolveConcatMembersSlicedInstruction(ConcatMemberVector &result,
			Instruction *I, bool isConcat, bool isBitRangeGet,
			uint64_t highBitNo, uint64_t lowBitNo) {
		//errs() << "resolveConcatMembersSlicedInstruction:" << *I << " ["
		//		<< highBitNo << ":" << lowBitNo << "]\n";
		assert(highBitNo > lowBitNo);
#ifndef NDEBUG
		uint64_t width0 = result.width();
#endif
		bool added = false;
		if (auto *BO = dyn_cast<BinaryOperator>(I)) {
			switch (BO->getOpcode()) {
			case Instruction::BinaryOps::And:
			case Instruction::BinaryOps::Or:
			case Instruction::BinaryOps::Xor: {
				// translate operands then build a new operand with new operands if required
				Value *op0 = resolveValue(I->getOperand(0), highBitNo,
						lowBitNo);
				Value *op1 = resolveValue(I->getOperand(1), highBitNo,
						lowBitNo);
				Value *res = nullptr;
				if (op0 == I->getOperand(0) && op1 == I->getOperand(1)) {
					// the instruction is already the thing which we are looking for
					res = I;
				} else {
					// create a part of original instruction for the specified slice
					builder.SetInsertPoint(I);
					switch (BO->getOpcode()) {
					case Instruction::BinaryOps::And:
						res = builder.CreateAnd(op0, op1);
						break;
					case Instruction::BinaryOps::Or:
						res = builder.CreateOr(op0, op1);
						break;
					case Instruction::BinaryOps::Xor:
						res = builder.CreateXor(op0, op1);
						break;
					default:
						llvm_unreachable("Should never get there");
					}
				}
				assert(res != nullptr);

				result.push_back(
						{ 0, res->getType()->getIntegerBitWidth(), res });

				added = true;
				break;
			}
			default:
				break;
			}
		} else if (auto *C = dyn_cast<CallInst>(I)) {
			if (isConcat) {
				uint64_t offset = 0;
				//errs() << "concat: " << *C << "\n";
				for (auto &O : C->args()) {
					uint64_t width = O->getType()->getIntegerBitWidth();
					//errs() << "L100 offset:" << offset << " " << " width:" << width << "\n";
					uint64_t end = offset + width;
					if (end <= lowBitNo) {
						// before selected bits
						offset += width;
						continue;
					}
					uint64_t _highBitNo = std::min(width, highBitNo - offset);
					uint64_t _lowBitNo;
					if (offset < lowBitNo) {
						_lowBitNo = lowBitNo - offset;
					} else {
						_lowBitNo = 0;
					}
					//errs() << "L367:" << width << " _highBitNo:" << _highBitNo
					//		<< " _lowBitNo:" << _lowBitNo << "\n";
					Value *_O = O.get();
					resolveConcatMembers(result, _O, _highBitNo, _lowBitNo);
					offset += width;
					if (offset >= highBitNo) {
						break;
					}
				}
				added = true;
			} else if (isBitRangeGet) {
				auto v = BitRangeGetOffsetWidthValue(C);
				resolveConcatMembers(result, v.value, v.offset + highBitNo,
						v.offset + lowBitNo);
				added = true;
			}
		} else if (auto *PHI = dyn_cast<PHINode>(I)) {
			uint64_t width = highBitNo - lowBitNo;
			OffsetWidthValue cacheKey = { lowBitNo, width, I };
			auto existing = commonSubexpressionCache.find(cacheKey);
			if (existing != commonSubexpressionCache.end()) {
				result.push_back( { 0, width, existing->second });
				added = true;
			} else {
				builder.SetInsertPoint(I);
				builder.SetInsertPoint(builder.GetInsertBlock(),
						++builder.GetInsertPoint());
				auto *newPhi = builder.CreatePHI(builder.getIntNTy(width),
						PHI->getNumIncomingValues(), PHI->getName());
				commonSubexpressionCache[cacheKey] = newPhi;
				for (auto &U : PHI->incoming_values()) {
					Value * newV;
					if (U->getType()->isIntegerTy()) {
						newV = resolveValue(U.get(), highBitNo, lowBitNo);
					} else {
						newV = U.get();
					}
					newPhi->addIncoming(newV, PHI->getIncomingBlock(U));
				}
			}
		} else if (dyn_cast<SelectInst>(I)) {
			llvm_unreachable("NotImplemented");
		}
		if (!added) {
			// instruction is not slicable
			result.push_back( { lowBitNo, highBitNo - lowBitNo, I });
		}
#ifndef NDEBUG
		uint64_t width1 = result.width();
		if (width0 + highBitNo - lowBitNo != width1) {
			errs() << *I << " width0:" << width0 << " highBitNo:" << highBitNo
					<< " lowBitNo:" << lowBitNo << " width1:" << width1 << "\n";
			llvm_unreachable("Incorrect number of bits was added");
		}
#endif
	}

	void resolveConcatMembers(ConcatMemberVector &result, Value *v,
			uint64_t highBitNo, uint64_t lowBitNo) {
		assert(v->getType()->getIntegerBitWidth() >= highBitNo);
		assert(highBitNo > lowBitNo);
		if (auto *I = dyn_cast<Instruction>(v)) {
			//errs() << "resolveConcatMembers:" << *v << " [" << highBitNo << ":"
			//		<< lowBitNo << "]\n";
			auto splits = splitPoints.find(I);
			auto *C = dyn_cast<CallInst>(I);
			bool isConcat = C && IsBitConcat(C);
			bool isBitRangeGet = C && IsBitRangeGet(C);
			if (isConcat || isBitRangeGet
					|| (splits != splitPoints.end()
							&& splits->second.size() != 0)) {
				// if there are split points it means that we have to use primitive slices generated from split points
				// and we must not use this composite value (because the split on primitive slice values is what this optimization does)
				bool doFillUpperBits = true;

				uint64_t lastOffset = 0;
				if (splits != splitPoints.end()) {
					bool exactStartFound = lowBitNo == 0;
					for (uint64_t splitPoint : splits->second) {
						assert(splitPoint > lastOffset);
						if (splitPoint < lowBitNo) {
							continue;
						} else if (splitPoint == lowBitNo) {
							lastOffset = splitPoint;
							exactStartFound = true;
							continue;
						}
						//errs() << "L174:" << *I << " splitPoint:" << splitPoint
						//		<< ", [" << highBitNo << ":" << lowBitNo
						//		<< "] lastOffset:" << lastOffset << "\n";
						assert(
								exactStartFound
										&& "The lowBitNo must be in split points because this is how split points were generated");
						assert(splitPoint <= highBitNo);
						resolveConcatMembersSlicedInstruction(result, I,
								isConcat, isBitRangeGet, splitPoint,
								lastOffset);
						lastOffset = splitPoint;
						if (splitPoint == highBitNo) {
							doFillUpperBits = false; // do not need to fill because we already added them
							break;
						}
					}
				}
				if (doFillUpperBits) {
					// errs() << "L191:" << *I << " splitPoint:" << ", [" << highBitNo
					// 		<< ":" << lowBitNo << "] lastOffset:" << lastOffset
					// 		<< "\n";
					assert(highBitNo <= I->getType()->getIntegerBitWidth());
					resolveConcatMembersSlicedInstruction(result, I, isConcat,
							isBitRangeGet, highBitNo,
							std::max(lastOffset, lowBitNo));
				}

			} else {
				// this instruction is not slicable we have to create a slice on top of it later
				result.push_back( { lowBitNo, highBitNo - lowBitNo, v });
			}
		} else {
			// this is constant slice it immediately
			auto *C = dyn_cast<ConstantInt>(v);
			uint64_t w = highBitNo - lowBitNo;
			auto *res = builder.getInt(C->getValue().lshr(lowBitNo).trunc(w));
			result.push_back( { 0, w, res });
		}
	}
	/*
	 * Rewrite value to a concatenation of the smallest non overlapping slices
	 * */
	Value* resolveValue(Value *v, uint64_t highBitNo, uint64_t lowBitNo) {
		OffsetWidthValue cacheKey = { lowBitNo, highBitNo - lowBitNo, v };
		auto existing = commonSubexpressionCache.find(cacheKey);
		if (existing != commonSubexpressionCache.end()) {
			return existing->second;
		}
		ConcatMemberVector concatMembers(builder, commonSubexpressionCache);
		resolveConcatMembers(concatMembers, v, highBitNo, lowBitNo);
		existing = commonSubexpressionCache.find(cacheKey);
		if (existing != commonSubexpressionCache.end()) {
			return existing->second;
		}
		Value *res = concatMembers.resolveValue(dyn_cast<Instruction>(v));
		commonSubexpressionCache[cacheKey] = res;
		return res;
	}

	bool resolveOperand(Use &O) {
		bool Changed = false;
		if (O->getType()->isIntegerTy()) {
			auto width = O->getType()->getIntegerBitWidth();
			auto *newO = resolveValue(O.get(), width, 0);
			if (O.get() != newO) {
				Changed = true;
				//errs() << "replacing:" << *O.get() << "\n    with:"
				//		<< *newO << "\n";
				assert(width == newO->getType()->getIntegerBitWidth());
			}
			O.set(newO);
		}
		return Changed;
	}
};

bool splitOnSplitPoints(
		const std::map<Instruction*, std::set<uint64_t>> &splitPoints,
		Function &F, IRBuilder<> &builder) {
	// collect instructions which will be removed
	std::set<Instruction*> toRemove;
	for (auto &B : F) {
		for (Instruction &I : B) {
			if (SlicedValueResolver::isInstructionSplitable(I)) {
				auto sp = splitPoints.find(&I);
				if (sp != splitPoints.end() && sp->second.size()) {
					toRemove.insert(&I);
				}
				if (auto *C = dyn_cast<CallInst>(&I)) {
					if (IsBitConcat(C) || IsBitRangeGet(C))
						toRemove.insert(&I);
				}
			}
		}
	}
	SlicedValueResolver svr(splitPoints, builder);
	bool Changed = toRemove.size() != 0;
	for (auto &B : F) {
		for (Instruction &I : B) {
			if (toRemove.find(&I) != toRemove.end()) {
				continue; // this instruction will be removed, we do not need to update it
			}
			// if instruction has a split point and it is splitable, instruction will be replaced so we skip it
			for (Use &O : I.operands()) {
				Changed |= svr.resolveOperand(O);
			}
		}
	}
	for (auto *I : toRemove) {
		I->eraseFromParent();
	}
	return Changed;
}

/*
 * There are several things to resolve:
 * 1. What are actually the inputs of non slicable operations.
 * 2. What are largest non-overlapping slices for each variable which are driven from unique source.
 * 3. Which variables for slice do exist and which and where should be created.
 */
PreservedAnalyses SlicesToIndependentVariablesPass::run(Function &F,
		FunctionAnalysisManager &AM) {
	//errs() << "SlicesToIndependentVariablesPass:\n";
	//F.dump();

	// for each instruction resolve segments of bits which are used independently
	auto splitPoints = collectSplitPoints(F);
	//for (auto &item : splitPoints) {
	//	errs() << *item.first;
	//	errs() << "    ";
	//	for (auto p : item.second) {
	//		errs() << p << " ";
	//	}
	//	errs() << "\n";
	//}
	// for each user of variable which have a split point resolve a new value
	// while looking trough the hierarchy of slices, concatenations and bitwise operators

	IRBuilder<> builder(F.getContext());
	bool Changed = splitOnSplitPoints(splitPoints, F, builder);

	// Move concatenations up in expression tree to reduce redundant slices
	// c = Concat(i[1] OP x, i[0] OP y)
	// to
	// c = i OP Concat(x, y)
	if (!Changed) {
		return PreservedAnalyses::all();
	}
	//F.dump();
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	return PA;
}

}
