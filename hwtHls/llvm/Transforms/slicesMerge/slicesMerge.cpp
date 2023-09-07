#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>
#include <map>
#include <sstream>

#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Scalar/NewGVN.h>
#include <llvm/IR/Dominators.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

using namespace llvm;
using namespace std;

//#define DBG_VERIFY_AFTER_EVERY_MODIFICATION 1

namespace hwtHls {


DceWorklist::SliceDict findSlices(Function &F) {
	DceWorklist::SliceDict slices;
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *CallI = dyn_cast<CallInst>(&I)) {
				if (IsBitRangeGet(CallI)) {
					auto *_offset = CallI->getArgOperand(1);
					if (auto *offset = dyn_cast<ConstantInt>(_offset)) {
						auto offsetInt = offset->getZExtValue();
						auto *bitVector = CallI->getArgOperand(0);
						auto curSlices = slices.find( { bitVector, offsetInt });
						if (curSlices == slices.end()) {
							slices[ { bitVector, offsetInt }] = { CallI };
						}
					}
				}
			}
		}
	}
	return slices;
}

PreservedAnalyses SlicesMergePass::run(Function &F,
		FunctionAnalysisManager &AM) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	{
		std::string errTmp = "hwtHls::SlicesMergePass got corrupted function ";
		llvm::raw_string_ostream errSS(errTmp);
		errSS << F.getName().str();
		errSS << "\n";
		if (verifyModule(*F.getParent(), &errSS)) {
			throw std::runtime_error(errSS.str());
		}
	}
#endif

	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	bool anyChange = false;
	bool firstRun = true;
	while (true) {
		// run phiShiftPatternRewrite rewriteConcat, mergeConsequentSlices, InstCombinePass, NewGVNPass
		// in loop while something is reduced
		bool change = false;
		DceWorklist::SliceDict slices = findSlices(F);
		auto createSlice = [&slices](IRBuilder<> *Builder, Value *bitVec,
				size_t lowBitNo, size_t bitWidth) {
			std::pair<Value*, uint64_t> key(bitVec, lowBitNo);
			auto cur = slices.find(key);
			if (cur == slices.end()) {
				auto _slice = CreateBitRangeGetConst(Builder, bitVec, lowBitNo,
						bitWidth);
				if (auto sliceCI = dyn_cast<CallInst>(_slice)) {
					if (IsBitRangeGet(sliceCI))
						slices[key] = { sliceCI };
				}
				return _slice;
			} else {
				for (auto sliceItem : cur->second) {
					if (sliceItem->getType()->getIntegerBitWidth()
							== bitWidth) {
						return (Value*) sliceItem;
					}
				}
				auto _slice = CreateBitRangeGetConst(Builder, bitVec, lowBitNo,
						bitWidth);
				if (auto sliceCI = dyn_cast<CallInst>(_slice)) {
					if (IsBitRangeGet(sliceCI))
						cur->second.push_back(sliceCI);
				}
				return _slice;
			}
		};

		for (BasicBlock &BB : F) {
			change |= phiShiftPatternRewrite(BB, createSlice);
		}
		DceWorklist dce(TLI, &slices);
		for (BasicBlock &BB : F) {
			for (auto I = BB.begin(); I != BB.end();) {
				if (dce.tryRemoveIfDead(*I, I)) {
					dce.runToCompletition(I);
					change = true;
					continue;
				}

				bool _changed = false;
				if (auto *CallI = dyn_cast<CallInst>(&*I)) {
					if (IsBitConcat(CallI)) {
						_changed = rewriteConcat(CallI, createSlice, dce);
					}
				}

				if (!_changed && !slices.empty()) {
					_changed |= mergeConsequentSlices(*I, slices, createSlice,
							dce);
				}
				change |= _changed;
				if (_changed) {
					change |= dce.tryRemoveIfDead(*I, I);
					change = dce.runToCompletition(I);
				} else {
					assert(
							dce.empty()
									&& "If there is something in DCE worklist there must have been some change");
					++I;
				}
			}
		}
		anyChange |= change;
		if (!firstRun && !change) {
			break;
		}
		firstRun = false;
		bool _change = false;
		InstCombinePass ic;
		auto ICres = ic.run(F, AM);
		if (!ICres.areAllPreserved()) {
			_change = true;
		}
		NewGVNPass gnv;
		auto gnvRes = gnv.run(F, AM);
		if (!gnvRes.areAllPreserved()) {
			_change = true;
		}
		anyChange |= _change;
	}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	{
		std::string errTmp = "hwtHls::SlicesMergePass corrupted function ";
		llvm::raw_string_ostream errSS(errTmp);
		errSS << F.getName().str();
		errSS << "\n";
		if (verifyModule(*F.getParent(), &errSS)) {
			throw std::runtime_error(errSS.str());
		}
	}
#endif
	if (anyChange) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}
}
