#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/IR/PatternMatch.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/Analysis/ValueTracking.h>

#include <hwtHls/llvm/targets/intrinsic/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;
using namespace hwtHls::PatternMatch;

namespace hwtHls {

void collectUntilDominatingBlock(const DominatorTree &DT,
		const BasicBlock &dominatingBB, BasicBlock &BB,
		SmallSet<BasicBlock*, 16> &blocks) {
	if (blocks.contains(&BB))
		return;
	if (&BB != &dominatingBB && DT.dominates(&dominatingBB, &BB)) {
		blocks.insert(&BB);
		for (auto pred : predecessors(&BB)) {
			collectUntilDominatingBlock(DT, dominatingBB, *pred, blocks);
		}
	}
}

bool isSafeToSpeculativelyExecuteInEoFThreading(Instruction &I) {
	if (I.isTerminator() || isa<PHINode>(&I))
		return false;
	if (isSafeToSpeculativelyExecute(&I))
		return true;
	if (auto II = dyn_cast<IntrinsicInst>(&I)) {
		switch (II->getIntrinsicID()) {
		case Intrinsic::ctpop:
		case Intrinsic::ctlz:
		case Intrinsic::cttz:
			return true;
		default:
			break;
		}
	}
	return false;
}

void collectExprUsedByAssume(Instruction &I, size_t depthLimit,
		std::set<Instruction*> &exprUsedByAssumes) {
	if (depthLimit == 0)
		return;
	if (exprUsedByAssumes.contains(&I))
		return;

	exprUsedByAssumes.insert(&I);
	switch (I.getOpcode()) {
	case Instruction::ICmp:
	case Instruction::And:
	case Instruction::Or:
	case Instruction::Xor: {
		for (Value *O : I.operand_values()) {
			if (auto OI = dyn_cast<Instruction>(O)) {
				collectExprUsedByAssume(*OI, depthLimit - 1, exprUsedByAssumes);
			}
		}
		break;
	}
	default:
		break;
	}
	return;
}

void collectSpeculableExpr(const SmallSet<BasicBlock*, 16> &blocks,
		LoadInst *srcLd, Value *expr, std::set<Instruction*> &speculableExprs,
		std::set<Instruction*> &exprUsedByAssumes) {
	auto *I = dyn_cast<Instruction>(expr);
	if (!I)
		return;
	if (isa<AssumeInst>(I)) {
		if (auto srcI = dyn_cast<Instruction>(I->getOperand(0)))
			collectExprUsedByAssume(*srcI, 3, exprUsedByAssumes);
		return;
	}
	if (!blocks.contains(I->getParent()))
		return;
	if (speculableExprs.contains(I))
		return;

	if (!isSafeToSpeculativelyExecuteInEoFThreading(*I))
		return;

	assert(
			(srcLd->getParent() != I->getParent() || srcLd->comesBefore(I))
					&& "srcLd must dominate all speculated instructions");

	//bool allUsersAreAssume = true;
	//for (auto *U : I->users()) {
	//	if (!isa<AssumeInst>(U)) {
	//		allUsersAreAssume = false;
	//		break;
	//	}
	//}
	//if (allUsersAreAssume)
	//	return; // skip rewrite of instructions used only by @llvm.assume
	// for (auto &O : I->operands()) {
	// 	if (auto OI = dyn_cast<Instruction>(O.get())) {
	// 		if (!speculableExprs.contains(OI))
	// 			return; // there is some operand which can not be speculated or we do not know it yet
	// 	}
	// }

	speculableExprs.insert(I);
	for (auto *U : I->users()) {
		collectSpeculableExpr(blocks, srcLd, U, speculableExprs,
				exprUsedByAssumes);
	}
}

Value* tryCloneBitRangeGet(IRBuilderBase &Builder, Instruction *UserI,
		std::function<Value* (size_t)> newOperandGetter) {
	if (isa<TruncInst>(UserI)) {
		return CreateBitRangeGetConst(&Builder, newOperandGetter(0), 0,
				UserI->getType()->getIntegerBitWidth());
	} else if (auto UserCI = dyn_cast<CallInst>(UserI)) {
		size_t width, offset;
		Value *V;
		if (match(UserCI, m_BitrangeGet(m_Value(V), offset, width))) {
			return CreateBitRangeGetConst(&Builder, newOperandGetter(0), offset,
					width);
		}
	}
	return nullptr;
}

void resolveBuilderInsertPointForSpeculationExitSelect(IRBuilderBase &Builder,
		Instruction *I, Value *ISpeculated) {
	Instruction *IP;
	if (auto ISpeculatedAsI = dyn_cast<Instruction>(ISpeculated)) {
		IP = ISpeculatedAsI->getNextNode();
	} else {
		IP = I->getNextNode();
	}
	Value *sliceSrcOp = nullptr;
	// skip potential bit slices
	while (isAnyFormOfBitRangeGet(IP, sliceSrcOp)) {
		IP = IP->getNextNode();
	}
	Builder.SetInsertPoint(IP);
}

void HwtHlsInstCombiner::_duplicateExprForEoFandNotEoFVariant(
		const std::set<Instruction*> &speculableExprs,
		llvm::Value *speculationCondition, bool speculationConditionVal,
		llvm::Instruction *I, llvm::Value *ISpeculated,
		std::map<Value*, Value*> &speculatedExprMap,
		std::map<Value*, Value*> &speculatedExprExitMap,
		std::set<Instruction*> &exprUsedByAssumes) {
	assert(I);
	assert(ISpeculated);
	assert(speculatedExprMap.find(I) == speculatedExprMap.end());
	assert(speculatedExprExitMap.find(I) == speculatedExprExitMap.end());

	SmallVector<const Use*, 16> Uses(make_pointer_range(I->uses()));
	if (exprUsedByAssumes.contains(I) && I != speculationCondition) {
		// keep original I as is for llvm.assume to use,
		// create new I for not speculated variant and later update
		// operands
		speculatedExprMap[I] = ISpeculated;
		Value *nonSpec = nullptr;
		if (I->getNumOperands())
			nonSpec = tryCloneBitRangeGet(Builder, I, [I](size_t opNo) {
				return I->getOperand(opNo);
			});
		if (!nonSpec) {
			auto _nonSpec = I->clone();
			_nonSpec->insertBefore(I->getIterator());
			nonSpec = _nonSpec;
		}
		Worklist.pushValue(nonSpec);
		I = dyn_cast<Instruction>(nonSpec);
		assert(I);
	}
	speculatedExprMap[I] = ISpeculated;
	Value *speculationExit = nullptr;
	for (const Use *U : Uses) {
		bool UserIsAlsoSpeculated = false;
		auto UserI = dyn_cast<Instruction>(U->getUser());
		if (UserI) {
			if (speculatedExprMap.find(UserI) == speculatedExprMap.end()) {
				// User can be speculated only after all operands were speculated
				// but user may use I in multiple operands
				// if this is the case the speculated version of UserI was already created
				continue;
			}
			if (isa<AssumeInst>(UserI))
				continue; // @llvm.assume calls are never speculated

			if (speculableExprs.contains(UserI)) {
				// is speculable try to construct speculated version of the user and propagate it
				UserIsAlsoSpeculated = true;
				SmallVector<Value*> newOperands;
				bool allUserInstrOperandsKnown = true;
				for (auto &O : UserI->operands()) {
					Value *OVal = O.get();
					if (auto OI = dyn_cast<Instruction>(OVal)) {
						if (speculableExprs.contains(OI)) {
							auto curSpec = speculatedExprMap.find(OI);
							if (curSpec == speculatedExprMap.end()) {
								allUserInstrOperandsKnown = false;
								break;
							} else {
								OVal = curSpec->second;
							}
						}
					}
					newOperands.push_back(OVal);
				}
				if (allUserInstrOperandsKnown) {
					assert(!isa<AssumeInst>(UserI));
					Value *SpeculatedUserI = nullptr;
					if (newOperands.size())
						SpeculatedUserI = tryCloneBitRangeGet(Builder, UserI,
								[&newOperands](size_t opNo) {
									return newOperands[opNo];
								});

					if (SpeculatedUserI == nullptr) {
						auto _SpeculatedUserI = UserI->clone();
						_SpeculatedUserI->insertAfter(UserI);
						for (size_t i = 0; i < newOperands.size(); i++) {
							replaceOperand(*_SpeculatedUserI, i,
									newOperands[i]);
						}
						SpeculatedUserI = _SpeculatedUserI;
					}
					SpeculatedUserI->setName(UserI->getName() + ".spec");
					Worklist.add(UserI);
					Worklist.addValue(SpeculatedUserI);
					_duplicateExprForEoFandNotEoFVariant(speculableExprs,
							speculationCondition, speculationConditionVal,
							UserI, SpeculatedUserI, speculatedExprMap,
							speculatedExprExitMap, exprUsedByAssumes);
				}
			}
		}
		if (!UserIsAlsoSpeculated) {
			if (!speculationExit) {
				if (I == speculationCondition) {
					assert(
							isa<ConstantInt>(ISpeculated)
									&& dyn_cast<ConstantInt>(ISpeculated)->getZExtValue()
											== speculationConditionVal);
					speculationExit = speculationCondition;
				} else {
					// set insert point after original and newly created speculation instruction and it slices
					resolveBuilderInsertPointForSpeculationExitSelect(Builder,
							I, ISpeculated);
					Value *TrueValue = ISpeculated;
					Value *FalseValue = I;
					if (!speculationConditionVal) {
						// speculation condition has inverse polarity
						std::swap(TrueValue, FalseValue);
					}
					auto name = I->getName() + ".specExit";
					speculationExit = Builder.CreateSelect(speculationCondition,
							TrueValue, FalseValue, name);
					Worklist.addValue(speculationExit);
				}
			}
			if (speculationExit != I) {
				// result of speculation is not speculation condition itself
				if (UserI) {
					assert(!isa<AssumeInst>(UserI));
					replaceOperand(*UserI, U->getOperandNo(), speculationExit);
				} else {
					U->getUser()->setOperand(U->getOperandNo(),
							speculationExit);
				}
			}
		}
	}
	if (speculationExit) {
		speculatedExprExitMap[I] = speculationExit;
	}
}

bool HwtHlsInstCombiner::tryImplementStreamReadEoFThreading(BranchInst &I) {
	// create a 2 versions of code between read and this branch
	// one for eof=1 which will remain as it is and
	// second for eof=0 which will have read mask replaced with all ones
	// because eof=0 implies that all mask bits are 1 (or empty==0)
	if (!I.isConditional())
		return false;

	// [todo] assume predicates may be oversimplified by this, e.g. predicate
	// which specifies that all mask bits are set to 1 is in form of "ld[x:y] == -1 or ~eof"
	// but by this it is reduced to "ld[x:y] == -1 or true" which is just true
	// thus assumption about mask is lost
	auto *EoF = I.getCondition();
	Value *_IOArg;
	size_t offset, width;
	if (match(EoF, m_BitrangeGet(m_Load(m_Value(_IOArg)), offset, width))
			&& isa<Argument>(_IOArg)) {
		//assert(
		//		width == 1
		//				&& "This must be 1b because it is BranchInst condition");
		auto IOArg = cast<Argument>(_IOArg);
		if (!StreamPropsAnalyzed) {
			// lazy load StreamProps
			for (auto p : StreamChannelFormatInfo::parseAllMetadata(F)) {
				StreamProps.insert(std::make_pair(p.ioArg, p));
			}
			StreamPropsAnalyzed = true;
		}
		const auto _streamProps = StreamProps.find(IOArg);
		if (_streamProps == StreamProps.end())
			return false; // this is not known stream IO

		const StreamChannelFormatInfo &streamProps = _streamProps->second;
		if (!streamProps.hasMask() && !streamProps.hasEmpty()) {
			return false; // this does not have any signalization of byte enable thus this opt. is not appliable
		}
		if (!streamProps.hasEoF()) {
			return false; // there is no EoF thus this is not appliable
		}
		if (offset != streamProps.getOffsetOfEoF()) {
			return false; // the condition bit is not EoF this is not where this opt should start
		}
		LoadInst *srcLd = cast<LoadInst>(cast<Instruction>(EoF)->getOperand(0));
		if (streamLoadsWithEoFThreadingApplied.contains(srcLd))
			return false;
		// collect all blocks from this to bb with load defined
		SmallSet<BasicBlock*, 16> blocks;
		collectUntilDominatingBlock(DT, *srcLd->getParent(), *I.getParent(),
				blocks);
		blocks.insert(srcLd->getParent());

		// collect all mask slices and eof, transitively collect speculatable expression in collected blocks
		// if expr ending with select eof, x, y it means that
		std::set<Instruction*> speculableExprs;
		std::set<Instruction*> exprUsedByAssumes;

		bool hasMask = streamProps.hasMask();
		bool hasEmpty = streamProps.hasEmpty();
		size_t maskOffset;
		size_t maskWidth;
		size_t emptyOffset;
		size_t emptyWidth;

		if (hasMask) {
			assert(!hasEmpty);
			maskOffset = streamProps.getOffsetOfMask();
			maskWidth = streamProps.getWidthOfMask();
		} else if (hasEmpty) {
			assert(!hasMask);
			emptyOffset = streamProps.getOffsetOfEmpty();
			emptyWidth = streamProps.getWidthOfEmpty();
		}
		SmallVector<Instruction*> maskValues;
		SmallVector<Instruction*> emptyValues;
		// add all masks and eof to speculableExprs because we would like to replace them in expressions as well
		auto EoFAsI = cast<Instruction>(EoF);
		speculableExprs.insert(EoFAsI);
		//speculableExprs.insert(maskValues.begin(), maskValues.end());
		for (Use &_U : srcLd->uses()) {
			auto U = _U.getUser();
			if (U == EoF) {
				collectSpeculableExpr(blocks, srcLd, U, speculableExprs,
						exprUsedByAssumes);
			} else if (match(U, m_BitrangeGet(m_Specific(srcLd), offset, width))
					&& ((hasMask && offset >= maskOffset
							&& offset + width <= maskOffset + maskWidth)
							|| (hasEmpty && offset >= emptyOffset
									&& offset + width
											<= emptyOffset + emptyWidth))) {
				// is select of some part of mask
				if (hasMask) {
					maskValues.push_back(cast<Instruction>(U));
				} else if (hasEmpty) {
					emptyValues.push_back(cast<Instruction>(U));
				} else {
					llvm_unreachable("has to have mask or empty");
				}
				collectSpeculableExpr(blocks, srcLd, U, speculableExprs,
					exprUsedByAssumes);
			}
		}
		//assert(
		//		exprUsedByAssumes.size()
		//				&& "There must be at least assume for EoF and mask/empty");
		// mover eof getter directly after LoadInst so it is asserted that it dominates all rewritten instructions
		EoFAsI->moveAfter(srcLd);

		// key is original expr which is rewritten for EoF=1
		// value is new expr which is written for EoF=0 (mask=all ones)
		// if any user is not in speculableExpr the speculation must be resolved by select between
		// EoF=0 and EoF=1 variant, this SelectInst is placed in speculatedExprExitMap
		std::map<Value*, Value*> speculatedExprMap;
		std::map<Value*, Value*> speculatedExprExitMap;
		std::map<Value*, Value*> backupExprForAssume;
		_duplicateExprForEoFandNotEoFVariant(speculableExprs, EoF, false,
				EoFAsI, Builder.getFalse(), speculatedExprMap,
				speculatedExprExitMap, exprUsedByAssumes);
		//size_t i = 0;
		for (auto m : maskValues) {
			auto mWidth = m->getType()->getIntegerBitWidth();
			auto speculatedMVal = Builder.getInt(APInt::getAllOnes(mWidth));
			_duplicateExprForEoFandNotEoFVariant(speculableExprs, EoF, false, m,
					speculatedMVal, speculatedExprMap, speculatedExprExitMap,
					exprUsedByAssumes);
		}
		for (auto e : emptyValues) {
			auto eWidth = e->getType()->getIntegerBitWidth();
			auto speculatedEVal = Builder.getInt(APInt::getZero(eWidth));
			_duplicateExprForEoFandNotEoFVariant(speculableExprs, EoF, false, e,
					speculatedEVal, speculatedExprMap, speculatedExprExitMap,
					exprUsedByAssumes);
		}

		// replace operands in original speculated expr to have value for EoF=1
		// (replace just EoF=1 because mask is unknown)
		auto b1 = Builder.getTrue();
		SmallVector<const Use*, 16> Uses(make_pointer_range(EoF->uses()));
		for (const Use *U : Uses) {
			auto UI = dyn_cast<Instruction>(U->getUser());
			if (UI && speculableExprs.contains(UI)
					&& !exprUsedByAssumes.contains(UI)
					&& speculatedExprMap.contains(UI)) {
				assert(!isa<AssumeInst>(UI));
				replaceOperand(*UI, U->getOperandNo(), b1);
				Worklist.push(UI);
			}
		}

		streamLoadsWithEoFThreadingApplied.insert(srcLd);
		return true;
	}

	return false;
}

}
