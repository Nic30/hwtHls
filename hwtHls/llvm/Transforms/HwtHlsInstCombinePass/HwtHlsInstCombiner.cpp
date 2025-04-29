#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Support/DebugCounter.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/ADT/Statistic.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerConcatAndSlices.h>

using namespace llvm;

STATISTIC(NumCombined, "Number of insts combined");
STATISTIC(NumConstProp, "Number of constant folds");
STATISTIC(NumDeadInst, "Number of dead inst eliminated");

DEBUG_COUNTER(VisitCounter, "instcombine-visit",
		"Controls which instructions are visited");

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
					return r;
				} else if (auto r = tryReduceIntrinsicInst_ctpopToCtlz(*II)) {
					return r;
				}
			}
			}
		} else if (IsBitConcat(CI)) {
			if (auto r = tryReduceConcatToZExt(*this, *CI)) {
				return r;
			} else if (auto r = tryReduceConstOpConcat(*this, *CI)) {
				return r;
			} else if (auto r = tryReduceConcatOnConcatOrContinuousSlices(*this,
					*CI)) {
				return r;
			}
		} else if (IsBitRangeGet(CI)) {
			BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(*this, *CI);
			if (auto r = tryReduceConstOpBitRangeGet(*this, *CI)) {
				return r;
			} else if (auto r = tryReduceBitRangeGetOnConcat(*this, *CI)) {
				return r;
			} else if (auto r = tryReduceBitRangeGetOnBitRangeGet(*this, *CI)) {
				return r;
			}
		} else if (auto r = tryReduceMergableFunction(*CI)) {
			return r;
		} else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
			if (auto r = _tryReduceCastHFloatTmpToHFloatTmpRaw(*CI)) {
				return r;
			}
		} else if (IsHwtHlsFp(CI)) {
			if (IsHwtHlsFpFRem(CI)) {
				if (auto r = _tryReduceFRemByPow2_to_HwtHlsFpCast(*CI)) {
					return r;
				}
			} else if (IsHwtHlsFpFMod(CI)) {
				if (auto r = _tryReduceFModByPow2_to_HwtHlsFpCast(*CI)) {
					return r;
				}
			} else if (IsHwtHlsFpFAdd(CI)) {
				if (auto r = _tryReduceHwtHlsFpFAdd(*CI)) {
					return r;
				}
			} else if (IsCastHFloatTmpToHFloatTmpRaw(CI)) {
				if (auto r = _tryReduceCastHFloatTmpRaw(*CI)) {
					return r;
				}
			}
		}
	} else if (auto CMPI = dyn_cast<CmpInst>(&I)) {
		//if (auto r = tryReduceCmpInst_hoistConstICmpOnConstArithAndSel(*CMPI)) {
		//	return r;
		//} else
		if (auto r = tryReduceUMinNe_to_ULT(*CMPI)) {
			return r;
		}
		if (auto ICMPI = dyn_cast<ICmpInst>(&I)) {
			if (auto r = tryReduceICmp_onTurncUMin(*ICMPI)) {
				return r;
			} else if (auto r = tryReduceICmpNEonPHI_to_UGT_or_ULT(*ICMPI)) {
				return r;
			}
		}

	} else if (auto *SI = dyn_cast<SelectInst>(&I)) {
		if (auto r = tryReduceSelectInst_unNegate(*SI)) {
			return r;
		}
		if (auto r = tryReduceSelectInst_toAndOr(*SI)) {
			return r;
		} else if (auto r = tryReduceSelectInst_extractCommonFromOperands(
				*SI)) {
			return r;
		} else if (auto r = tryReduceSelectInst_deepAdderChainToBitCounts(*SI,
				Options.bitcountExtractionTreshold)) {
			return r;
		} else if (auto r =
				tryReduceSelectInst_selectOfImpliedBitsOrZero_toConcat(*SI)) {
			return r;
		}
	} else if (auto EI = dyn_cast<ZExtInst>(&I)) {
		if (auto r = tryReduceZExt_onZExt(*this, *EI)) {
			return r;
		} else if (auto r = tryReduceZExt_onTurncUMin(*EI)) {
			return r;
		}
	} else if (auto TI = dyn_cast<TruncInst>(&I)) {
		TruncInstMoveIntoSliceSuccessorsOfSrcOperand(*this, *TI);
	} else if (auto BI = dyn_cast<BinaryOperator>(&I)) {
		switch (BI->getOpcode()) {
		case BinaryOperator::FMul:
			if (Options.hwtHlsFpCombining) {
				if (auto r = tryReduceFMulByPow2_to_HwtHlsFpSh(*BI)) {
					return r;
				}
			}
			break;
		case BinaryOperator::FDiv:
			if (Options.hwtHlsFpCombining) {
				if (auto r = tryReduceFDivByPow2_to_HwtHlsFpSh(*BI)) {
					return r;
				}
			}
			break;
		default:
			if (auto r = tryReduceAndOfAssumedPredicates(*BI)) {
				return r;
			} else if (auto r = tryReduceAndAndWithCommon(*BI)) {
				return r;
			} else if (auto r = tryReduceOrOnBits_toNE(*BI)) {
				return r;
			} else if (auto r = tryReduceAndWithEq_to_widerEq(*BI)) {
				return r;
			}
			break;
		}
	} else if (auto BR = dyn_cast<BranchInst>(&I)) {
		if (Options.streamReadEoFThreading
				&& tryImplementStreamReadEoFThreading(*BR)) {
			return nullptr;
		}
	}
	if (auto r = simplifyInstruction(&I, SQ)) {
		return replaceInstUsesWith(I, r);
	}

	return nullptr;
}
}
