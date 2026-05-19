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
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				} else if (auto r = tryReduceIntrinsicInst_ctpopToCtlz(*II)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
				break;
			}
			case Intrinsic::fshl: {
				if (auto r = tryReduceIntrinsicInst_fshlConstSh(*II)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
				break;
			}
			case Intrinsic::fshr: {
				if (auto r = tryReduceIntrinsicInst_fshrConstSh(*II)) {
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
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceConstOpConcat(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceConcatOnConcatOrContinuousSlices(*this,
					*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (IsBitRangeGet(CI)) {
			BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(*CI);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			if (auto r = tryReduceConstOpBitRangeGet(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnConcat(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceBitRangeGetOnBitRangeGet(*this, *CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (auto r = tryReduceMergableFunctionInSequence(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
			if (auto r = _tryReduceCastHFloatTmpToHFloatTmpRaw(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		} else if (IsHwtHlsFp(CI)) {
			if (IsHwtHlsFpFCmp(CI)) {
				if (auto r = _tryReduceHwtHlsFCmp(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFRem(CI)) {
				if (auto r = _tryReduceFRemByPow2_to_HwtHlsFpCast(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFMod(CI)) {
				if (auto r = _tryReduceFModByPow2_to_HwtHlsFpCast(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFAdd(CI)) {
				if (auto r = _tryReduceHwtHlsFpFAdd(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			} else if (IsHwtHlsFpFSub(CI)) {
			    if (auto r = tryReduceHwtHlsFpSub_to_addNeg(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
			    }
			}else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
				if (auto r = _tryReduceCastHFloatTmpRaw(*CI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			}
		}
	} else if (auto CMPI = dyn_cast<CmpInst>(&I)) {
		if (auto r = tryReduceCmpInst_hoistConstICmpOnConstArithAndSel(*CMPI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceUMinNe_to_ULT(*CMPI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto ICMPI = dyn_cast<ICmpInst>(&I)) {
			if (auto r = tryReduceCmpInst_cmpOnMaskToBitGet(*ICMPI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceICmp_onTurncUMin(*ICMPI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceICmpNEonPHI_to_UGT_or_ULT(*ICMPI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			}
		}
	} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
		if (auto r = tryReduceSelectInst_unNegate(*SI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceMergableFunctionInSelect(*SI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_toAndOr(*SI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_extractCommonFromOperands(
				*SI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceSelectInst_deepAdderChainToBitCounts(*SI,
				Options.bitcountExtractionTreshold)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r =
				tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat(*SI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		}
	} else if (auto EI = dyn_cast<ZExtInst>(&I)) {
		if (auto r = tryReduceZExt_onZExt(*this, *EI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		} else if (auto r = tryReduceZExt_onTurncUMin(*EI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return r;
		}
	} else if (auto TI = dyn_cast<TruncInst>(&I)) {
		TruncInstMoveIntoSliceSuccessorsOfSrcOperand(*TI);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
	} else if (auto BI = dyn_cast<BinaryOperator>(&I)) {
		switch (BI->getOpcode()) {
		case BinaryOperator::FMul:
			if (Options.hwtHlsFpCombining) {
				if (auto r = tryReduceFMulByPow2_to_HwtHlsFpSh(*BI)) {
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
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
#endif
					return r;
				}
			}
			break;
		default:
			if (auto r = tryReduceAndOfAssumedPredicates(*BI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceAndAndWithCommon(*BI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceOrOfAssumedPredicates(*BI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceOrOnBits_toNE(*BI)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));
#endif
				return r;
			} else if (auto r = tryReduceAndWithEq_to_widerEq(*BI)) {
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
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			return nullptr;
		}
	}
	if (auto r = simplifyInstruction(&I, SQ)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
		return replaceInstUsesWith(I, r,
				I.getName().starts_with(IMPLICATION_CACHE_INSTR_NAME_PREFIX));
	}

	return nullptr;
}
}
