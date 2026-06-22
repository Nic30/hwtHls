#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Support/DebugCounter.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/ADT/Statistic.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerConcatAndSlices.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/Transforms/utils/bitSliceInstrMove.h>

using namespace llvm;

STATISTIC(NumCombined, "Number of insts combined");
STATISTIC(NumConstProp, "Number of constant folds");
STATISTIC(NumDeadInst, "Number of dead inst eliminated");

DEBUG_COUNTER(VisitCounter, "instcombine-visit",
		"Controls which instructions are visited");

// #define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

namespace hwtHls {

HwtHlsInstCombiner::HwtHlsInstCombiner(BuilderTy &Builder,
		llvm::SimplifyQuery SQ, llvm::InstructionWorklist &Worklist,
		HwtHlsInstCombinePassOptions optConfig, llvm::Function &F) :
		HwtHlsInstCombinerMixin<HwtHlsInstCombiner>(Builder, SQ, Worklist, F,
				::NumCombined, ::NumConstProp, ::NumDeadInst, ::VisitCounter), Options(
				optConfig), StreamPropsAnalyzed(false) {
	assert(SQ.DT);
	assert(SQ.AC);
	_dbgIrInstrCombineChangeCallbackFn = Options._dbgIrInstrCombineChangeCallbackFn;
}

bool HwtHlsInstCombiner::runOptimizationsAfterWorklistEmpty() {
	return pruneInvertedCmpDuplicatesInBlocks(F) || !Worklist.isEmpty();
}

Instruction* HwtHlsInstCombiner::runOnInstr(Instruction &I) {
	if (auto CI = dyn_cast<CallInst>(&I)) {
		if (auto *II = dyn_cast<IntrinsicInst>(CI)) {
			Intrinsic::ID IID = II->getIntrinsicID();
			switch (IID) {
			case Intrinsic::ctpop: {
				if (auto r = tryReduceIntrinsicInst_ctpopReduceBitwidth(*II)) {
					lastOptRuleName = "tryReduceIntrinsicInst_ctpopReduceBitwidth";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				} else if (auto r = tryReduceIntrinsicInst_ctpopToCtlz(*II)) {
					lastOptRuleName = "tryReduceIntrinsicInst_ctpopToCtlz";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
				break;
			}
			case Intrinsic::fshl: {
				if (auto r = tryReduceIntrinsicInst_fshlConstSh(*II)) {
					lastOptRuleName = "tryReduceIntrinsicInst_fshlConstSh";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
				break;
			}
			case Intrinsic::fshr: {
				if (auto r = tryReduceIntrinsicInst_fshrConstSh(*II)) {
					lastOptRuleName = "tryReduceIntrinsicInst_fshrConstSh";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
				break;
			}
			}
		} else if (IsBitConcat(CI)) {
			if (auto r = tryReduceConcatToZExt(*this, *CI)) {
			lastOptRuleName = "tryReduceConcatToZExt";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceConstOpConcat(*this, *CI)) {
				lastOptRuleName = "tryReduceConstOpConcat";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceConcatOnConcatOrContinuousSlices(*this,
					*CI)) {
				lastOptRuleName = "tryReduceConcatOnConcatOrContinuousSlices";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (IsBitRangeGet(CI)) {
			if (BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(*CI)) {
				lastOptRuleName = "BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand";
			}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			if (auto r = tryReduceConstOpBitRangeGet(*this, *CI)) {
				lastOptRuleName = "tryReduceConstOpBitRangeGet";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnConcat(*this, *CI)) {
				lastOptRuleName = "tryReduceBitRangeGetOnConcat";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnBitRangeGet(*this, *CI)) {
				lastOptRuleName = "tryReduceBitRangeGetOnBitRangeGet";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (auto r = tryReduceMergableFunctionInSequence(*CI)) {
			lastOptRuleName = "tryReduceMergableFunctionInSequence";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
			if (auto r = _tryReduceCastHFloatTmpToHFloatTmpRaw(*CI)) {
				lastOptRuleName = "_tryReduceCastHFloatTmpToHFloatTmpRaw";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (IsHwtHlsFp(CI)) {
			if (IsHwtHlsFpFCmp(CI)) {
				if (auto r = _tryReduceHwtHlsFCmp(*CI)) {
					lastOptRuleName = "_tryReduceHwtHlsFCmp";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFRem(CI)) {
				if (auto r = _tryReduceFRemByPow2_to_HwtHlsFpCast(*CI)) {
					lastOptRuleName = "_tryReduceFRemByPow2_to_HwtHlsFpCast";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFMod(CI)) {
				if (auto r = _tryReduceFModByPow2_to_HwtHlsFpCast(*CI)) {
					lastOptRuleName = "_tryReduceFModByPow2_to_HwtHlsFpCast";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFAdd(CI)) {
				if (auto r = _tryReduceHwtHlsFpFAdd(*CI)) {
					lastOptRuleName = "_tryReduceHwtHlsFpFAdd";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFSub(CI)) {
			    if (auto r = tryReduceHwtHlsFpSub_to_addNeg(*CI)) {
					lastOptRuleName = "tryReduceHwtHlsFpSub_to_addNeg";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
			    }
			}else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
				if (auto r = _tryReduceCastHFloatTmpRaw(*CI)) {
					lastOptRuleName = "_tryReduceCastHFloatTmpRaw";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			}
		}
	} else if (auto CMPI = dyn_cast<CmpInst>(&I)) {
		if (auto r = tryReduceCmpInst_hoistConstICmpOnConstArithAndSel(*CMPI)) {
			lastOptRuleName = "tryReduceCmpInst_hoistConstICmpOnConstArithAndSel";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceUMinNe_to_ULT(*CMPI)) {
		lastOptRuleName = "tryReduceUMinNe_to_ULT";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto ICMPI = dyn_cast<ICmpInst>(&I)) {
			if (auto r = tryReduceCmpInst_cmpOnMaskToBitGet(*ICMPI)) {
				lastOptRuleName = "tryReduceCmpInst_cmpOnMaskToBitGet";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceICmp_onTurncUMin(*ICMPI)) {
				lastOptRuleName = "tryReduceICmp_onTurncUMin";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceICmpNEonPHI_to_UGT_or_ULT(*ICMPI)) {
				lastOptRuleName = "tryReduceICmpNEonPHI_to_UGT_or_ULT";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		}
	} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
		if (auto r = tryReduceSelectInst_unNegate(*SI)) {
			lastOptRuleName = "tryReduceSelectInst_unNegate";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceMergableFunctionInSelect(*SI)) {
			lastOptRuleName = "tryReduceMergableFunctionInSelect";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_toAndOr(*SI)) {
			lastOptRuleName = "tryReduceSelectInst_toAndOr";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_extractCommonFromOperands(
				*SI)) {
			lastOptRuleName = "tryReduceSelectInst_extractCommonFromOperands";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_deepAdderChainToBitCounts(*SI,
				Options.bitcountExtractionTreshold)) {
			lastOptRuleName = "tryReduceSelectInst_deepAdderChainToBitCounts";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r =
				tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat(*SI)) {
			lastOptRuleName = "tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		}
	} else if (auto EI = dyn_cast<ZExtInst>(&I)) {
		if (auto r = tryReduceZExt_onZExt(*this, *EI)) {
			lastOptRuleName = "tryReduceZExt_onZExt";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceZExt_onTurncUMin(*EI)) {
			lastOptRuleName = "tryReduceZExt_onTurncUMin";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		}
	} else if (auto TI = dyn_cast<TruncInst>(&I)) {
		if (TruncInstMoveIntoSliceSuccessorsOfSrcOperand(*TI)) {
			lastOptRuleName = "TruncInstMoveIntoSliceSuccessorsOfSrcOperand";
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
	} else if (auto BI = dyn_cast<BinaryOperator>(&I)) {
		switch (BI->getOpcode()) {
		case BinaryOperator::FMul:
			if (Options.hwtHlsFpCombining) {
				if (auto r = tryReduceFMulByPow2_to_HwtHlsFpSh(*BI)) {
					lastOptRuleName = "tryReduceFMulByPow2_to_HwtHlsFpSh";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			}
			break;
		case BinaryOperator::FDiv:
			if (Options.hwtHlsFpCombining) {
				if (auto r = tryReduceFDivByPow2_to_HwtHlsFpSh(*BI)) {
					lastOptRuleName = "tryReduceFDivByPow2_to_HwtHlsFpSh";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			}
			break;
		default:
			if (auto r = tryReduceAndOfAssumedPredicates(*BI)) {
				lastOptRuleName = "tryReduceAndOfAssumedPredicates";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceAndAndWithCommon(*BI)) {
				lastOptRuleName = "tryReduceAndAndWithCommon";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceOrOfAssumedPredicates(*BI)) {
				lastOptRuleName = "tryReduceOrOfAssumedPredicates";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceOrOnBits_toNE(*BI)) {
				lastOptRuleName = "tryReduceOrOnBits_toNE";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceAndWithEq_to_widerEq(*BI)) {
				lastOptRuleName = "tryReduceAndWithEq_to_widerEq";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
			break;
		}
	} else if (auto BR = dyn_cast<BranchInst>(&I)) {
		if (Options.streamReadEoFThreading
				&& tryImplementStreamReadEoFThreading(*BR)) {
			lastOptRuleName = "tryImplementStreamReadEoFThreading";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return nullptr;
		}
	}
	if (auto r = simplifyInstruction(&I, SQ)) {
		lastOptRuleName = "HwtHlsInstCombiner - llvm::simplifyInstruction";
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
		return replaceInstUsesWith(I, r,
				I.getName().starts_with(IMPLICATION_CACHE_INSTR_NAME_PREFIX));
	}

	return nullptr;
}
}
