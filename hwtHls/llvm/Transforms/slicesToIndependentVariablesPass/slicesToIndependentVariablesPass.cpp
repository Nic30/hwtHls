#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <map>
#include <set>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/detectSplitPoints.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#define DEBUG_TYPE "slices-to-independent-variables"

using namespace llvm;
//#undef LLVM_DEBUG
//#define LLVM_DEBUG(dbg) dbg

namespace hwtHls {

class SlicedValueResolver {
public:

	const InstrSet &noSplitInstrs;
	const SplitPoints &splitPoints;
	IRBuilder<> &builder;
	std::unordered_map<OffsetWidthValue, Value*> commonSubexpressionCache;
	std::set<Instruction*> &toRemove;
	// bool & CFGWasChanged;

	SlicedValueResolver(const InstrSet &noSplitInstrs,
			const SplitPoints &splitPoints, IRBuilder<> &builder,
			std::set<Instruction*> &toRemove //, bool & CFGWasChanged
			) :
			noSplitInstrs(noSplitInstrs), splitPoints(splitPoints), builder(
					builder), toRemove(toRemove) //, CFGWasChanged(CFGWasChanged)
	{
	}

	void cancelRemoveOfBitConcatAndBitRangeGetExpr(Value *V) {
		if (auto *C = dyn_cast<CallInst>(V)) {
			if (IsBitConcat(C) || IsBitRangeGet(C)) {
				auto cur = toRemove.find(C);
				if (cur != toRemove.end())
					toRemove.erase(cur);
				for (llvm::Use &opU : C->args()) {
					cancelRemoveOfBitConcatAndBitRangeGetExpr(opU.get());
				}
			}
		} else if (auto *C = dyn_cast<CastInst>(V)) {
			auto cur = toRemove.find(C);
			if (cur != toRemove.end())
				toRemove.erase(cur);
			for (llvm::Use &opU : C->operands()) {
				cancelRemoveOfBitConcatAndBitRangeGetExpr(opU.get());
			}
		}
	}

	static bool isInstructionSplitable(const InstrSet &noSplitInstrs,
			Instruction &I) {
		if (noSplitInstrs.find(&I) != noSplitInstrs.end())
			return false;
		if (auto *BO = dyn_cast<BinaryOperator>(&I)) {
			switch (BO->getOpcode()) {
			case Instruction::BinaryOps::And:
			case Instruction::BinaryOps::Or:
			case Instruction::BinaryOps::Xor:
				return true;
			default:
				break;
			};
		} else if (isa<PHINode>(&I)) {
			return true;
		} else if (isa<SelectInst>(&I)) {
			return true;
		} else if (auto *C = dyn_cast<CallInst>(&I)) {
			if (IsBitConcat(C) || IsBitRangeGet(C))
				return true;
		} else if (isa<CastInst>(&I)) {
			return true;
		}

		return false;
	}
	// static bool InstructionDominatesInSameBlock(Instruction & I0, Instruction & I1) {
	// 	// :returns: true if I0 is predecessor of I1
	// 	const BasicBlock & BB = *I0.getParent();
	// 	assert(I1.getParent() == &BB);
	// 	for (auto I = I1.getIterator(); I->getIterator() != BB.begin(); --I) {
	// 		if (I0.getIterator() == I) {
	// 			return true;
	// 		}
	// 	}
	// 	return false;
	// }

	void resolveConcatMembers(ConcatMemberVector &result, Value *v,
			uint64_t highBitNo, uint64_t lowBitNo) {
		assert(v->getType()->getIntegerBitWidth() >= highBitNo);
		assert(highBitNo > lowBitNo);
		if (auto *I = dyn_cast<Instruction>(v)) {
			LLVM_DEBUG(
					dbgs() << "resolveConcatMembers:" << *v << " [" << highBitNo
							<< ":" << lowBitNo << "]\n");
			auto splits = splitPoints.find(I);
			auto *C = dyn_cast<CallInst>(I);
			bool isConcat = C && IsBitConcat(C);
			bool isBitRangeGet = C && !isConcat && IsBitRangeGet(C);
			bool hasNoSplit = noSplitInstrs.find(I) != noSplitInstrs.end();
			if (!hasNoSplit
					&& (isConcat || isBitRangeGet
							|| (splits != splitPoints.end()
									&& splits->second.size() != 0))) {
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
						LLVM_DEBUG(
								dbgs() << "L" << __LINE__ << ":" << *I << " splitPoint:" << splitPoint << ", [" << highBitNo << ":" << lowBitNo << "] lastOffset:" << lastOffset << "\n");
						assert(
								exactStartFound
										&& "The lowBitNo must be in split points because this is how split points were generated");
						assert(
								splitPoint <= highBitNo
										&& "The splitpoint must satisfy width of the sliced vector and there must be every splitpoint in splitPoints, the highBitNo as well");
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
					// fill upper bits of concatenation, if there are no splitpoints this fills whole value
					LLVM_DEBUG(
							dbgs() << "L" << __LINE__ << ":" << *I << " splitPoint:" << ", [" << highBitNo << ":" << lowBitNo << "] lastOffset:" << lastOffset << "\n");
					assert(highBitNo <= I->getType()->getIntegerBitWidth());
					resolveConcatMembersSlicedInstruction(result, I, isConcat,
							isBitRangeGet, highBitNo,
							std::max(lastOffset, lowBitNo));
				}

			} else {
				// this instruction is not slicable we have to create a slice on top of it later
				result.push_back( { lowBitNo, highBitNo - lowBitNo, v });
			}
		} else if (auto *CI = dyn_cast<CastInst>(v)) {
			errs() << *CI << "\n";
			llvm_unreachable("[todo]");
		} else if (auto *C = dyn_cast<ConstantInt>(v)) {
			// this is constant slice it immediately
			uint64_t w = highBitNo - lowBitNo;
			APInt v = C->getValue().lshr(lowBitNo);
			auto *res = builder.getInt(v.getBitWidth() != w ? v.trunc(w) : v);
			result.push_back( { 0, w, res });
		} else if (isa<PoisonValue>(v)) {
			uint64_t w = highBitNo - lowBitNo;
			auto *res = PoisonValue::get(builder.getIntNTy(w));
			result.push_back( { 0, w, res });
		} else if (isa<UndefValue>(v)) {
			uint64_t w = highBitNo - lowBitNo;
			auto *res = UndefValue::get(builder.getIntNTy(w));
			result.push_back( { 0, w, res });
		} else {
			errs() << *v << "\n";
			llvm_unreachable("Unsupported type of value");
		}
	}
	/*
	 * Rewrite value to a concatenation of the smallest non overlapping slices
	 * */
	Value* resolveValue(Value *v, uint64_t highBitNo, uint64_t lowBitNo) {
		if (auto *I = dyn_cast<Instruction>(v)) {
			if (noSplitInstrs.find(I) != noSplitInstrs.end())
				return v;
		}
		OffsetWidthValue cacheKey = { lowBitNo, highBitNo - lowBitNo, v };
		auto existing = commonSubexpressionCache.find(cacheKey);
		if (existing != commonSubexpressionCache.end()) {
			return existing->second;
		}
		ConcatMemberVector concatMembers(builder, &commonSubexpressionCache);
		resolveConcatMembers(concatMembers, v, highBitNo, lowBitNo);
		existing = commonSubexpressionCache.find(cacheKey);
		if (existing != commonSubexpressionCache.end()) {
			return existing->second;
		}
		Value *res = concatMembers.resolveValue(dyn_cast<Instruction>(v));
		cancelRemoveOfBitConcatAndBitRangeGetExpr(res);
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
				LLVM_DEBUG(
						dbgs() << "replacing:" << *O.get() << "\n    with:"
								<< *newO << "\n");
				assert(width == newO->getType()->getIntegerBitWidth());
			}
			O.set(newO);
		}
		return Changed;
	}

	void resolveConcatMembersSlicedInstruction(ConcatMemberVector &result,
			Instruction *I, bool isConcat, bool isBitRangeGet,
			uint64_t highBitNo, uint64_t lowBitNo) {
		LLVM_DEBUG(
				dbgs() << "resolveConcatMembersSlicedInstruction:" << *I << " ["
						<< highBitNo << ":" << lowBitNo << "]\n");
		assert(highBitNo > lowBitNo);
#ifndef NDEBUG
		uint64_t width0 = result.width();
#endif
		bool added = false;
		if (auto *BO = dyn_cast<BinaryOperator>(I)) {
			added = resolveConcatMembersSlicedInstruction_BinaryOperator(
					highBitNo, lowBitNo, BO, I, result);
		} else if (auto *C = dyn_cast<CallInst>(I)) {
			added = resolveConcatMembersSlicedInstruction_CallInst(isConcat,
					lowBitNo, highBitNo, isBitRangeGet, C, result);
		} else if (auto *PHI = dyn_cast<PHINode>(I)) {
			added = resolveConcatMembersSlicedInstruction_PHINode(highBitNo,
					lowBitNo, BO, PHI, result);
		} else if (auto SI = dyn_cast<SelectInst>(I)) {
			added = resolveConcatMembersSlicedInstruction_SelectInst(highBitNo,
					lowBitNo, SI, result);
		} else if (auto CI = dyn_cast<CastInst>(I)) {
			added = resolveConcatMembersSlicedInstruction_CastInst(lowBitNo,
					highBitNo, CI, result);
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

	bool resolveConcatMembersSlicedInstruction_BinaryOperator(
			uint64_t highBitNo, uint64_t lowBitNo, llvm::BinaryOperator *BO,
			Instruction *I, ConcatMemberVector &result) {
		bool added = false;
		switch (BO->getOpcode()) {
		case Instruction::BinaryOps::And:
		case Instruction::BinaryOps::Or:
		case Instruction::BinaryOps::Xor: {
			// translate operands then build a new operand with new operands if required
			Value *op0 = resolveValue(I->getOperand(0), highBitNo, lowBitNo);
			Value *op1 = resolveValue(I->getOperand(1), highBitNo, lowBitNo);
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
			result.push_back( { 0, res->getType()->getIntegerBitWidth(), res });
			added = true;
			break;
		}
		default:
			break;
		}
		return added;
	}

	bool resolveConcatMembersSlicedInstruction_CallInst(bool isConcat,
			uint64_t lowBitNo, uint64_t highBitNo, bool isBitRangeGet,
			llvm::CallInst *C, ConcatMemberVector &result) {
		bool added = false;
		if (isConcat) {
			uint64_t offset = 0;
			LLVM_DEBUG(dbgs() << "concat: " << *C << "\n");
			for (auto &O : C->args()) {
				uint64_t width = O->getType()->getIntegerBitWidth();
				LLVM_DEBUG(
						dbgs() << "L" << __LINE__ << " offset:" << offset << " " << " width:" << width << "\n");
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
				LLVM_DEBUG(
						dbgs() << "L" << __LINE__ << ":" << width << " _highBitNo:" << _highBitNo << " _lowBitNo:" << _lowBitNo << "\n");
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

		return added;
	}

	bool resolveConcatMembersSlicedInstruction_CastInst(uint64_t lowBitNo,
			uint64_t highBitNo, CastInst *I, ConcatMemberVector &result) {
		bool added = false;
		auto opSrc = I->getOperand(0);
		size_t srcWidth = opSrc->getType()->getIntegerBitWidth();
		Value *res = nullptr;
		if (lowBitNo < srcWidth) {
			res = resolveValue(opSrc, std::min(highBitNo, srcWidth), lowBitNo);
			if (srcWidth < highBitNo) {
				// selecting bits from base value
				auto resTy = builder.getIntNTy(highBitNo - lowBitNo);
				builder.SetInsertPoint(I);
				switch (I->getOpcode()) {
				case Instruction::ZExt:
					res = builder.CreateZExt(res, resTy, I->getName());
					break;
				case Instruction::SExt:
					res = builder.CreateSExt(res, resTy, I->getName());
					break;
				case Instruction::BitCast:
					res = builder.CreateBitCast(res, resTy, I->getName());
					break;
				default:
					errs() << *I << "\n";
					llvm_unreachable("Unsupported type of cast operator");
				}
			}
		} else {
			// selecting bits from extension
			auto resTy = builder.getIntNTy(highBitNo - lowBitNo);
			builder.SetInsertPoint(I);
			switch (I->getOpcode()) {
			case Instruction::ZExt:
				res = ConstantInt::get(resTy, 0);
				break;
			case Instruction::SExt: {
				auto msb = resolveValue(opSrc, srcWidth, srcWidth - 1);
				for (size_t i = lowBitNo; i < highBitNo; ++i) {
					result.push_back( { 0, 1, msb });
				}
				added = true;
				break;
			}
			default:
				errs() << *I << "\n";
				llvm_unreachable("Unsupported type of cast operator");
			}
		}
		if (!added) {
			assert(res != nullptr);
			result.push_back( { 0, res->getType()->getIntegerBitWidth(), res });
		}
		added = true;
		return added;
	}

	bool resolveConcatMembersSlicedInstruction_PHINode(uint64_t highBitNo,
			uint64_t lowBitNo, llvm::BinaryOperator *BO, PHINode *PHI,
			ConcatMemberVector &result) {
		bool added = false;
		uint64_t width = highBitNo - lowBitNo;
		OffsetWidthValue cacheKey = { lowBitNo, width, PHI };
		auto existing = commonSubexpressionCache.find(cacheKey);
		if (existing != commonSubexpressionCache.end()) {
			result.push_back( { 0, width, existing->second });
			added = true;
		} else {
			IRBuilder_setInsertPointBehindPhi(builder, PHI);
			// inserting after last phi
			auto *newPhi = builder.CreatePHI(builder.getIntNTy(width),
					PHI->getNumIncomingValues(), PHI->getName());
			commonSubexpressionCache[cacheKey] = newPhi;
			// prefill incoming values to have a valid PHI, for SplidEdge call
			//auto undefV = UndefValue::get(newPhi->getType());
			//for (auto& BB: PHI->blocks()) {
			//	newPhi->addIncoming(undefV, BB);
			//}

			// BasicBlock & ParentBB = *PHI->getParent();
			// size_t predIndex = 0;
			for (auto const& [PredBB, U] : llvm::zip(PHI->blocks(),
					PHI->incoming_values())) {
				Value *newV;
				if (U->getType()->isIntegerTy()) {
					newV = resolveValue(U.get(), highBitNo, lowBitNo);
				} else {
					newV = U.get();
				}
				// [note] This is not required because all phis at the top of block are resolved atomically at once.
				// check for case where value depends on some predecessor PHINode in this block
				// if (auto otherPhi = dyn_cast<PHINode>(newV)) {
				// 	if (otherPhi->getParent() == &ParentBB) {
				// 		if (InstructionDominatesInSameBlock(*otherPhi, *newPhi)) {
				// 			// if this is a case we have to create a temporary variable using PHINode
				// 			BasicBlock * tmpBB;
				// 			if (PredBB != &ParentBB && PredBB->getSinglePredecessor()) {
				// 				// check if we can place tmp var PHINode in predecessor block
				// 				assert(otherPhi->getParent() != PredBB && "It should already be checked that otherPhi is in same block as PHI and it is not PredBB");
				// 				tmpBB = &*PredBB;
				// 			} else {
				// 				// or we have to create a new block
				// 				tmpBB = SplitEdge(&*PredBB, &ParentBB,
				// 				                      /*DT */ nullptr, /*LI*/ nullptr,
				// 				                      /*MSSAU*/ nullptr,
				// 				                      /*BBName*/"");
				// 				CFGWasChanged = true;
				// 			}
				// 			{
				// 				IRBuilder<>::InsertPointGuard g(builder);
				// 				builder.SetInsertPoint(tmpBB);
				// 				if (tmpBB->begin() != tmpBB->end()) {
				// 					IRBuilder_setInsertPointBehindPhi(builder, &*tmpBB->begin());
				// 				}
				// 				auto tmpPhi = builder.CreatePHI(otherPhi->getType(), 1, otherPhi->getName() + ".tmp");
				// 				auto predPred = tmpBB->getSinglePredecessor();
				// 				assert(predPred && "We just build a block which has a single predecessor");
				// 				tmpPhi->addIncoming(newV, tmpBB->getSinglePredecessor());
				// 				newV = tmpPhi;
				// 			}
				// 		}
				// 	}
				// }
				newPhi->addIncoming(newV, PredBB);
				// newPhi->setIncomingValue(predIndex, newV);
				// ++predIndex;
			}
			result.push_back( { 0, width, newPhi });
			added = true;
		}
		return added;
	}

	bool resolveConcatMembersSlicedInstruction_SelectInst(uint64_t highBitNo,
			uint64_t lowBitNo, SelectInst *I, ConcatMemberVector &result) {
		bool added = false;
		// translate operands then build a new operand with new operands if required
		Value *opCond = resolveValue(I->getOperand(0), 1, 0);
		Value *opTrue = resolveValue(I->getOperand(1), highBitNo, lowBitNo);
		Value *opFalse = resolveValue(I->getOperand(2), highBitNo, lowBitNo);
		Value *res = nullptr;
		if (opCond == I->getOperand(0) && opTrue == I->getOperand(1)
				&& opFalse == I->getOperand(2)) {
			// the instruction is already the thing which we are looking for
			res = I;
		} else {
			// create a part of original instruction for the specified slice
			builder.SetInsertPoint(I);
			res = builder.CreateSelect(opCond, opTrue, opFalse, I->getName());
		}
		assert(res != nullptr);
		result.push_back( { 0, res->getType()->getIntegerBitWidth(), res });
		added = true;
		return added;
	}

};

bool splitOnSplitPoints(const InstrSet &noSplitInstrs,
		const SplitPoints &splitPoints, Function &F, IRBuilder<> &builder,
		FunctionAnalysisManager &FAM) {
	// collect instructions which will be removed
	std::set<Instruction*> toRemove;
	for (auto &B : F) {
		for (Instruction &I : B) {
			if (SlicedValueResolver::isInstructionSplitable(noSplitInstrs, I)) {
				auto sp = splitPoints.find(&I);

				if (sp != splitPoints.end() && sp->second.size()) {
					toRemove.insert(&I);
				} else if (auto *C = dyn_cast<CallInst>(&I)) {
					if (IsBitConcat(C) || IsBitRangeGet(C))
						toRemove.insert(&I);
				} else if (isa<CastInst>(&I)) {
					toRemove.insert(&I);
				}
			}
		}
	}
	SlicedValueResolver svr(noSplitInstrs, splitPoints, builder, toRemove);
	bool Changed = toRemove.size() != 0;
	for (auto &B : F) {
		for (Instruction &I : B) {
			if (toRemove.find(&I) != toRemove.end()) {
				continue; // this instruction will be removed, we do not need to update it
			}
			// if instruction has a split point and it is splitable, instruction will be replaced so we skip it
			LLVM_DEBUG(dbgs() << "Resolving operands for:" << I << "\n");
			for (Use &O : I.operands()) {
				Changed |= svr.resolveOperand(O);
				//removeBitConcatAndBitRangeGetExprFromSet(toRemove, O.get());
			}
			LLVM_DEBUG(dbgs() << "Resolved operands:" << I << "\n");
		}
	}
#ifndef NDEBUG
	for (auto *I : toRemove) {
		for (User *u : I->users()) {
			assert(isa<Instruction>(u));
			if (toRemove.find(dyn_cast<Instruction>(u)) == toRemove.end()) {
				dbgs() << "I:" << *I << "\n";
				dbgs() << "user: " << dyn_cast<Instruction>(u) << " " << *u
						<< "\n";
				//for (auto & toRm: toRemove) {
				//	dbgs() << "toRm: " << toRm << " " << *toRm << '\n';
				//}
				writeCFGToDotFile(F,
						"after.SlicesToIndependentVariablesPass.dot", FAM);
				llvm_unreachable(
						"Removed instruction still used by something which is not removed");
			}
		}
	}
#endif

	for (auto *I : toRemove) {
		I->replaceAllUsesWith(PoisonValue::get(I->getType()));
		I->eraseFromParent();
	}

	return Changed;
}

//void assertPhiDoesNotUsePredecessorPhi(const Function &F) {
//	for (auto & BB: F) {
//		std::set<const PHINode*> phis;
//		for (const PHINode & PHI: BB.phis()) {
//			for (const Use & IV: PHI.incoming_values()) {
//				if (const PHINode * PhiIV = dyn_cast<const PHINode>(IV.get())) {
//					if (phis.find(PhiIV) != phis.end()) {
//						llvm_unreachable("PHI in block uses other PHI defined before it in the same block");
//					}
//				}
//			}
//			phis.insert(&PHI);
//		}
//	}
//}

/*
 * There are several things to resolve:
 * 1. What are actually the inputs of non slicable operations.
 * 2. What are largest non-overlapping slices for each variable which are driven from unique source.
 * 3. Which variables for slice do exist and which and where should be created.
 */
PreservedAnalyses SlicesToIndependentVariablesPass::run(Function &F,
		FunctionAnalysisManager &AM) {
	//assertPhiDoesNotUsePredecessorPhi(F);

	// for each instruction resolve segments of bits which are used independently
	InstrSet noSplitInstrs;
	auto splitPoints = collectSplitPoints(F, noSplitInstrs);
	//errs() << "Split points:\n";
	//for (auto &item : splitPoints) {
	//	errs() << *item.first;
	//	errs() << "    [";
	//	for (auto p : item.second) {
	//		errs() << p << " ";
	//	}
	//	errs() << "]\n";
	//}
	//writeCFGToDotFile(F, "before.SlicesToIndependentVariablesPass.dot", AM);
	// for each user of variable which have a split point resolve a new value
	// while looking trough the hierarchy of slices, concatenations and bitwise operators

	IRBuilder<> builder(F.getContext());
	bool Changed = splitOnSplitPoints(noSplitInstrs, splitPoints, F, builder,
			AM);

	// Move concatenations up in expression tree to reduce redundant slices
	// c = Concat(i[1] OP x, i[0] OP y)
	// to
	// c = i OP Concat(x, y)
	if (!Changed) {
		return PreservedAnalyses::all();
	}
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	return PA;
}

}
