#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_phiToLogicalExpr.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

//void _redursivelyCollectPredecessorBlocks(BasicBlock * BB, BasicBlock * handle, SmallPtrSet<BasicBlock*, 16> &blocks) {
//	assert(&BB->getParent()->getEntryBlock() != BB && "BB should have been dominated by handle");
//	blocks.insert(BB);
//	if (BB == handle)
//		return;
//	for (auto* pred: llvm::predecessors(BB)) {
//		if (!blocks.contains(pred) && pred != handle)
//			_redursivelyCollectPredecessorBlocks(pred, handle, blocks);
//	}
//}

// attempt to hoist to first pred BB
// :attention: there may be some blocks in between blocks inpredecChain
bool HwtHlsSimplifyCFGPass_phiToLogicalExpr_hoist(
		CfgFragmentChainOfblocksWithSameSucc &predecChain,
		SmallPtrSet<BasicBlock*, 16> &blocksToHoistFrom) {
	bool Changed = false;

	bool first = true;
	BasicBlock * pred;
	for (auto &BBItem : predecChain.blocks) {
		if (first) {
			first = false;
			pred = BBItem.BB;
			continue;
		}
		if (BBItem.BB->getUniquePredecessor() != pred)
			return false; // this is not just a simple chain, there are some additional blocks between the blocks of chain
		blocksToHoistFrom.insert(BBItem.BB);
		// _redursivelyCollectPredecessorBlocks(BBItem.BB, pred, blocksToHoistFrom);
		pred = BBItem.BB;
	}

	first = true;
	auto FirstBBTerm = predecChain.blocks[0].BB->getTerminator()->getIterator();
	for (auto &BBItem : predecChain.blocks) {
		if (first) {
			first = false;
			continue;
		}
		for (Instruction &I : make_early_inc_range(*BBItem.BB)) {
			assert(
					!isa<PHINode>(&I)
							&& "This can not be phi because all non-first blocks should have just 1 predecessor");
			if (I.mayHaveSideEffects() || I.isVolatile() || I.isTerminator()) {
				continue; // can not move
			} else if (any_of(I.operands(), [&blocksToHoistFrom](Use &op) {
				if (auto OpI = dyn_cast<Instruction>(op.get())) {
					return blocksToHoistFrom.contains(OpI->getParent());
				}
				return false;
			})) {
				// // can not hoist because it depends on something which can not be hoisted
				continue;
			}
			I.moveBefore(*FirstBBTerm->getParent(), FirstBBTerm);
			Changed = true;
		}
	}
	return Changed;
}

bool HwtHlsSimplifyCFGPass_phiToLogicalExpr(IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, llvm::BasicBlock &exitBB,
		bool &exprChanged) {
	if (exitBB.phis().empty())
		return false; // nothing to optimize

	auto &DT = DTU.getDomTree();
	for (BasicBlock *Pred : predecessors(&exitBB)) {
		if (DT.dominates(&exitBB, Pred)) {
			// exitBB is a loop header
			// if this is a case it it is not safe to remove phis
			return false;
		}
	}
	CfgFragmentChainOfblocksWithSameSucc _predecChainTmp;
	auto _predecChain = CfgFragmentChainOfblocksWithSameSucc::detect(exitBB,
			_predecChainTmp);
	if (!_predecChain.has_value())
		return false; // there is no chain of predecessors which we could use to optimize phis
	//if (_predecChain.value().blocks.back().toExitBrCond)
	//	return false; // last block has conditional branch, this pattern accepts only unconditional
	//// because wee need all blocks to converge at exit block

	auto predecChain = _predecChain.value();
	if (predecChain.blocks.size() == 2
			&& all_of(exitBB.phis(), [](const PHINode &phi) {
				return phi.getType()->isIntegerTy(1);
			})) {
		// optimize because there are phis suitable for conversion to logical expression
	} else if (predecChain.blocks.size() < 2)
		return false; // too simple, this transformation is not required

	// :note: this should not change dominance as 1st block in chain should dominate all others including exitBB
	// thus PHIs can be replaced with SelectInst etc.
	assert(DT.dominates(predecChain.blocks[0].BB, &exitBB));

	SmallPtrSet<BasicBlock*, 16> blocksToHoistFrom;
	// :attention: can not "or" exprChange to CfgChange because EarlyCSEPass hoist would cause inf. loop
	exprChanged |= HwtHlsSimplifyCFGPass_phiToLogicalExpr_hoist(predecChain,
			blocksToHoistFrom);
	bool CfgChange = false;
	for (auto &BBItem : predecChain.blocks) {
		auto Term = dyn_cast<BranchInst>(BBItem.BB->getTerminator());
		if (Term->isConditional()) {
			if (auto CI = dyn_cast<Instruction>(Term->getCondition())) {
				if (blocksToHoistFrom.contains(CI->getParent())) {
					return CfgChange; // can not continue with extraction of PHIs because the condition was not hoisted
				}
			}
		}
	}
	// apply this only as a last step after there nothing inside of blocks
	for (auto &BBItem : predecChain.blocks) {
		if (BBItem.BB == predecChain.blocks.front().BB)
			continue; // allow some instructions in top most block
		if (BBItem.BB->getTerminator()->getIterator() != BBItem.BB->begin()) {
			for (auto I = BBItem.BB->begin();
					I != BBItem.BB->getTerminator()->getIterator(); I++) {
				Value *v;
				if (!match(&*I,
						m_Intrinsic<Intrinsic::IndependentIntrinsics::assume>(
								m_Value(v)))) {
					// block contains something so even if we reduce this phi,
					// it is not possible to remove the predecessor block
					return CfgChange;
				}
			}
			// block contains only llvm.assume which is allowed as it is expected that it will be moved later
		}
	}

	for (auto &PHI : make_early_inc_range(exitBB.phis())) {
		bool allIncommingValuesDominatingBB = true;
		for (auto &v : PHI.incoming_values()) {
			if (auto I = dyn_cast<Instruction>(v.get())) {
				if (!DT.dominates(I, &exitBB)) {
					allIncommingValuesDominatingBB = false;
					break;
				}
			}
		}
		if (!allIncommingValuesDominatingBB)
			continue;
		if (auto V = HwtHlsSimplifyCFGPass_phiToLogicalExpr(Builder, DL, AC,
				predecChain, PHI)) {
			// If V is a new unnamed instruction, take the name from the old one.
			if (V->use_empty() && isa<Instruction>(V) && !V->hasName()
					&& PHI.hasName())
				V->takeName(&PHI);

			PHI.replaceAllUsesWith(V);
			PHI.eraseFromParent();

			CfgChange = true;
		}
	}

	if (exitBB.phis().empty()) {
		// if we successfully removed all phis try to merge predecessor block sequence to this exit block
		// there may still be some instructions which can not be hoisted in this case, at least
		// most bottom blocks are merged
		bool mostBottom = true;
		for (const CfgFragmentChainOfblocksWithSameSucc::BasicBlockAndBrCond &BBItem : reverse(
				predecChain.blocks)) {
			BasicBlock *BB = BBItem.BB;
			if (predecChain.blocks.front().BB != BB
					&& BB->begin() == BB->getTerminator()->getIterator()) {
				// if is empty block with just terminator merge it with successor
				// if it is in block in predecessor chain
				if (!MergeBlockIntoPredecessor(BB, &DTU, /*LI*/nullptr, /*MSSAU*/
				nullptr, /*MemDep*/nullptr, /*PredecessorWithTwoSuccessors*/
				!mostBottom)) {
					break;
				}
			}
			if (mostBottom)
				mostBottom = false;
		}
	}

	return CfgChange;
}

void checkForZeroAndAllOnes(Value *V, bool &isZero, bool &isAllOnes) {
	isZero = false;
	isAllOnes = false;
	if (ConstantInt *C = dyn_cast<ConstantInt>(V)) {
		auto CV = C->getValue();
		if (CV.isZero())
			isZero = true;
		else if (CV.isAllOnes())
			isAllOnes = true;
	}
}

using BasicBlockAndBrCondVectorIterator = llvm::SmallVector<CfgFragmentChainOfblocksWithSameSucc::BasicBlockAndBrCond>::const_iterator;
// collect conditions for exit (negate=false) or continue (negate=true) in chain of blocks
void getConditions(IRBuilderBase &Builder,
		iterator_range<BasicBlockAndBrCondVectorIterator> blocks, bool negate,
		SmallVector<Value*> &res) {
	for (const CfgFragmentChainOfblocksWithSameSucc::BasicBlockAndBrCond &BB : blocks) {
		auto Cond = BB.toExitBrCond;
		if (Cond) {
			if (BB.toExitBrCondIsNegated != negate) {
				Cond = Builder.CreateNot(Cond);
			}
			res.push_back(Cond);
		} else {
			Cond = Builder.getInt1(!negate); // condition is not specified and it is default exit condition
		}
	}
}

/*
 * This function checks if value v is a specific value for funel shift left with specified shift amount
 * :param v: checked shifted value
 * :param a: value which is shifted out
 * :param b: value which is shifted in from lsb side of a
 * :param ShiftAmt: shift amount for fshl operation
 * */
inline bool isFshlOf(llvm::Value *v, llvm::Value *a, llvm::Value *b,
		size_t ShiftAmt) {
	size_t width = v->getType()->getIntegerBitWidth();
	if (ShiftAmt == 0) {
		return v == a;
	} else if (ShiftAmt == width) {
		return v == b;
	} else {
		// test for v[sh:] == a bottom width-sh bits
		//          v[:sh] == b top sh bits
		auto aConst = dyn_cast<ConstantInt>(a);
		auto bConst = dyn_cast<ConstantInt>(b);
		if (aConst && bConst) {
			if (auto vC = dyn_cast<ConstantInt>(v)) {
				return vC->getValue()
						== (aConst->getValue().shl(ShiftAmt)
								| bConst->getValue().lshr(width - ShiftAmt));
			}
		} else if (auto *CI = dyn_cast<CallInst>(v)) {
			if (IsBitConcat(CI)) {
				// if b is sext it means that msb is replicated
				// check also the case where msb is explicitly replicated in this concatenation

				// :note: this does not check that a is sext and is shifted out, to check this you should call this function
				//  with a,b swapped
				if (auto bSExt = dyn_cast<SExtInst>(b)) {
					auto bSExtSrc = bSExt->getOperand(0);
					if (bSExtSrc->getType()->getIntegerBitWidth() == 1) {
						// b is a 1 bit copied by sext
						// check if v = concat(bBit+, ..., 0)
						if (ShiftAmt == 1 && aConst
								&& aConst->getValue().isZero()) {
							// check for specific case where
							Value *ZExtSrc;
							if (match(v, m_ZExt(m_Value(ZExtSrc)))
									&& ZExtSrc == bSExtSrc) {
								return true;
							}
						}
						// check for variant with concat
						size_t bSrcBitsAtBeginRemaining = ShiftAmt;
						for (auto &concatArg : CI->args()) {
							if (bSrcBitsAtBeginRemaining != 0) {
								// check that concat bits starts with ShiftAmt sized prefix of bSExtSrc bit (from lsb side)
								if (concatArg.get() != bSExtSrc) {
									return false;
								}
								--bSrcBitsAtBeginRemaining;
							} else {
								// check that remaining bits after bSExtSrc are taken from a bottom bits
								if (aConst) {
									if (concatArg.getOperandNo()
											== CI->arg_size() - 1) {
										if (auto msbBits =
												dyn_cast<ConstantInt>(
														concatArg.get())) {
											if (msbBits->getValue()
													== (aConst->getValue()
															<< ShiftAmt)) {
												return true;
											}
										}
									}
								}
							}
						}
					}
				}
			}
			// do not search further as this is should be concatenation
			// (fshl may be implemented using shl|lshr but this check is not implemented there)
		}
		return false;

	}
}

llvm::Value* HwtHlsSimplifyCFGPass_phiToLogicalExpr(IRBuilderBase &Builder,
		const llvm::DataLayout &DL, llvm::AssumptionCache *AC,
		CfgFragmentChainOfblocksWithSameSucc &predecChain, llvm::PHINode &PHI) {
	// :attention: this expects all branch condition defs to be hoisted before terminator of the first predecessor BB in chain
	if (!PHI.getType()->isIntegerTy())
		return nullptr;
	// Checked patterns:
	// [0], [1], [2], [4] are not just for 1b, true represents all-ones
	// [0] [false{n}, x{m}] // value conditionally set from some point
	//                        ->    And(!bb.c for bb in n, x)
	// [1] [true{n}, x{m}] // value condition from some point
	//                        ->     Or( bb.c for bb in n, x)
	// [2] [x{n}, false{m}] // value cleared from some point
	//                        ->  And(Or(bb.c for bb in n), x)
	// [3] [x{n}, true{m}] // value set from some point
	//                        -> Or(x, Or(bb.c for bb in m))

	// [4] [x{n}, y{m}]
	//                        -> select (Or(bb.c for bb in n)), x, y

	//     :note: sh = ctlz(~concat(bb.c for bb))
	// [5] [fshl(0, sext x, sh)] e.g. [i3 0, concat(x, 0, 0), concat(x, x, 0), concat(x, x, x)]
	//     :note: new bits x are shifted in from lsb side
	//                        -> fshl(0, zext x, sh)
	// [6] [fshl(sext x, 0, sh)] (prev case but reversed)  e.g. [concat(x, x, x), concat(x, x, 0), concat(x, 0, 0), i3 0]
	//     :note: bits x are shifted out to right
	//                                  -> fshl(zext x, 0, sh)
	// :note: fshl(0, sext x, ctlz(~concat(bb.c for bb))) can then be folded to concat(allPredecCisOne() & bb.c for bb)
	//     which then can be pruned further by assumptions about format of the mask
	//     possibly just to concat(bb.c for bb)

	// :note: bit counts are related to a vector which is a concatenation of conditions in predecessor block
	// [7] cttz [0, 1, 2, ... max-1]
	//                        -> cttz(concat(bb.c for bb in m))
	// [8] count trailing ones [max-1, max-2, ..., 0]
	//                        -> cttz(~concat(bb.c for bb in m))
	Builder.SetInsertPoint(predecChain.blocks.front().BB->getTerminator());
	std::vector<Value*> values;
	values.reserve(predecChain.blocks.size());

	size_t commonPrefixLen = 0;	// [0], [1], [2], [3]
	for (auto &BBItem : predecChain.blocks) {
		auto *V = PHI.getIncomingValueForBlock(BBItem.BB);
		if (values.empty()) {
			++commonPrefixLen;

		} else if (commonPrefixLen == values.size()) { // if is continuous sequence of prefix value (lsb to msb)
			if (values.back() == V)
				++commonPrefixLen;
		}
		values.push_back(V);
	}
	if (commonPrefixLen == values.size()) {
		return values.front(); // case [x{n}]
	}

	size_t commonSuffixLen = 0; // [0], [1], [2], [3]
	Value *suffix = values.back();
	for (Value *V : reverse(values)) {
		if (V == suffix) {
			++commonSuffixLen;
		} else {
			break;
		}
	}
	bool isBeginZero = false; // [0], [4], [6]
	bool isBeginAllOnes = false; // [1], [7]
	bool isEndZero = false; // [0], [4], [6]
	bool isEndAllOnes = false; // [1], [7]
	checkForZeroAndAllOnes(values.front(), isBeginZero, isBeginAllOnes);
	checkForZeroAndAllOnes(values.back(), isEndZero, isEndAllOnes);

	auto &blocks = predecChain.blocks;
	SmallVector<Value*> conditions;
	if (commonPrefixLen + commonSuffixLen == values.size()) {
		auto prefixBBs = make_range(blocks.begin(),
				blocks.begin() + commonPrefixLen);
		auto suffixBBs = make_range(blocks.begin() + commonPrefixLen,
				blocks.end());
		auto Ty = PHI.getType();
		size_t valWidth = PHI.getType()->getIntegerBitWidth();
		if (isBeginZero) {
			// [0] [false{n}, x{m}] // value conditionally set from some point
			//                        ->    And(!bb.c for bb in n, x)
			getConditions(Builder, prefixBBs, /*negate*/true, conditions);
			if (valWidth == 1) {
				conditions.push_back(values.back());
				pruneImpliedConditionsAndLastLikelyMostSpecific(conditions,
						Builder, DL, AC, /*DT*/nullptr,
						&*Builder.GetInsertPoint());
				auto c = Builder.CreateAnd(conditions);
				return c;
			} else {
				auto c = Builder.CreateAnd(conditions);
				pruneImpliedConditionsAndLastLikelyMostSpecific(conditions,
						Builder, DL, AC, /*DT*/nullptr,
						&*Builder.GetInsertPoint());
				return Builder.CreateSelect(c, values.back(),
						Builder.getIntN(valWidth, 0));
			}
		} else if (isBeginAllOnes) {
			// [1] [true{n}, x{m}] // value condition from some point
			//                        ->     Or( bb.c for bb in n, x)
			getConditions(Builder, prefixBBs, /*negate*/false, conditions);
			if (valWidth == 1) {
				conditions.push_back(values.back());
				return Builder.CreateOr(conditions);
			} else {
				auto c = Builder.CreateOr(conditions);
				return Builder.CreateSelect(c, ConstantInt::getAllOnesValue(Ty),
						values.back());
			}
		} else if (isEndZero) {
			// [2] [x{n}, false{m}] // value cleared from some point
			//                        ->  And(Or(bb.c for bb in n), x)
			getConditions(Builder, prefixBBs, /*negate*/false, conditions);
			if (valWidth == 1) {
				return Builder.CreateAnd(Builder.CreateOr(conditions),
						values.front());
			} else {
				auto c = Builder.CreateAnd(conditions);
				return Builder.CreateSelect(c, values.front(),
						ConstantInt::get(Ty, 0));
			}

		} else if (isEndAllOnes) {
			// [3] [x{n}, true{m}] // value set from some point
			//                        -> Or(x, Or(bb.c for bb in m))
			getConditions(Builder, suffixBBs, /*negate*/true, conditions);
			if (valWidth == 1) {
				conditions.push_back(values.front());
				return Builder.CreateOr(conditions);
			} else {
				auto c = Builder.CreateAnd(conditions);
				return Builder.CreateSelect(c, values.front(),
						ConstantInt::getAllOnesValue(Ty));
			}

		} else {
			// [4] [x{n}, y{m}]
			//                        -> select (Or(bb.c for bb in n)), x, y
			getConditions(Builder, prefixBBs, /*negate*/false, conditions);
			return Builder.CreateSelect(Builder.CreateOr(conditions),
					values.front(), values.back());
		}
	} else {
		auto v0 = values.front();
		auto vLast = values.back();
		getConditions(Builder, blocks, /*negate*/false, conditions);
		// :note: example of fshl %r = call i8 @llvm.fshl.i8(i8 %x, i8 %y, i8 %z)  ; %r = i8: msb_extract((concat(x, y) << (z % 8)), 8)
		// :note: concat is in format lsb first

		// [5] [fshl(0, sext x, sh)] e.g. [i3 0, concat(x, 0, 0), concat(x, x, 0), concat(x, x, x)]
		//     :note: new bits x are shifted in from lsb side
		//                        -> fshl(0, zext x, concat(bb.c for each bb))
		// [6] [fshl(sext x, 0, sh)] (prev case but reversed)  e.g. [concat(x, x, x), concat(x, x, 0), concat(x, 0, 0), i3 0]
		//     :note: bits x are shifted out to right
		//                        -> fshl(zext x, 0, concat(bb.c for each bb))
		auto *Ty = v0->getType();
		auto getShiftOperand = [&Builder, &conditions, Ty](
				bool negateInputsOfCttz) {
			Value *_fshlShOp = CreateBitConcat(&Builder, conditions);
			if (negateInputsOfCttz)
				_fshlShOp = Builder.CreateNot(_fshlShOp);
			Value *fshlShOp = Builder.CreateIntrinsic(Intrinsic::cttz, {
					_fshlShOp->getType() }, { _fshlShOp,
			/*isZeroPoisonous*/Builder.getFalse() });
			fshlShOp = Builder.CreateZExtOrTrunc(fshlShOp, Ty);
			return fshlShOp;
		};
		if (isPow2(PHI.getNumIncomingValues())) {
			// if not isPow2 then NotImplemented: guess possible initial shifts
			// search for [5]
			bool match = true;
			for (size_t i = 0; i < values.size(); ++i) {
				if (!isFshlOf(values[i], v0, vLast, i)) {
					match = false;
					break;
				}
			}
			if (match) {
				// [5] matched
				auto fshlShOp = getShiftOperand(true);
				return Builder.CreateIntrinsic(Intrinsic::fshl, { Ty, Ty, Ty },
						{ v0, vLast, fshlShOp });
			}
			// search for [6]
			for (size_t i = 0; i < values.size(); ++i) {
				if (!isFshlOf(values[values.size() - i - 1], vLast, v0, i)) {
					match = false;
					break;
				}
			}
			if (match) {
				// [6] matched
				auto fshlShOp = getShiftOperand(true);
				return Builder.CreateIntrinsic(Intrinsic::fshl, { Ty, Ty, Ty },
						{ vLast, v0, fshlShOp });
			}
		}

		// :note: bit counts are related to a vector which is a concatenation of conditions in predecessor block
		// [7] count trailing zeros cttz([0, 1, 2, ... max-1] + offset)
		//                        -> ctlz(concat(bb.c for bb in m)) + offset
		// [8] count trailing ones ctto([max-1, max-2, ..., 0] + offset)
		//                        -> cttz(~concat(bb.c for bb in m)) + offset
		// check if all values are constant
		for (auto v : values) {
			if (!isa<ConstantInt>(v)) {
				return nullptr; // can not be bit count because some value is not constant
			}
		}
		int linearStep =
				dyn_cast<ConstantInt>(values[1])->getValue().getZExtValue()
						- dyn_cast<ConstantInt>(values[0])->getValue().getZExtValue();
		if (linearStep == 1 || linearStep == -1) {
			bool hasSameStepBetweenEachValue = true;
			for (auto lastV = values.begin() + 1; lastV != values.end();
					++lastV) {
				auto nextV = lastV + 1;
				if (nextV == values.end())
					break; // there is no next value and we verified linear step between all items in value sequence

				int _linearStep =
						dyn_cast<ConstantInt>(*nextV)->getValue().getZExtValue()
								- dyn_cast<ConstantInt>(*lastV)->getValue().getZExtValue();
				if (_linearStep != linearStep) {
					hasSameStepBetweenEachValue = false;
					break;
				}
			}
			if (hasSameStepBetweenEachValue) {
				auto v0 = dyn_cast<ConstantInt>(values[0]);
				if (linearStep == 1) {
					auto bitCntVal = getShiftOperand(false); // [7]
					return Builder.CreateAdd(v0, bitCntVal); // add offset
				} else if (linearStep == -1) {
					auto bitCntVal = getShiftOperand(true); // [8]
					return Builder.CreateAdd(v0, bitCntVal); // add offset
				}
			}
		}
	}

	return nullptr;
}

}
