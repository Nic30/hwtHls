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
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewriteConcat.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/slicesMerge/rewritePhiShift.h>
#include <hwtHls/llvm/Transforms/slicesMerge/mergeConsequentSlices.h>

using namespace llvm;
using namespace std;

//#define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <hwtHls/llvm/Transforms/utils/irConsistencyChecks.h>
#endif

namespace hwtHls {

inline void verifyAfterUpdate(Function &F, DceWorklist *dce, const std::string &msg) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	if (dce)
		dce->assertSlicesConsistency();
	verifyUsesList(F);
	std::string errTmp = "hwtHls::SlicesMergePass ";
	llvm::raw_string_ostream errSS(errTmp);
	errSS << " ";
	errSS << F.getName().str();
	errSS << "\n";
	if (verifyModule(*F.getParent(), &errSS)) {
		throw std::runtime_error(errSS.str());
	}
#endif
}

inline void verifyAfterUpdate(Function &F, DceWorklist &dce, const std::string &msg) {
	verifyAfterUpdate(F, &dce, msg);
}

DceWorklist::SliceDict findSlices(Function &F) {
	DceWorklist::SliceDict slices;
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			auto sliceItem = OffsetWidthValue::fromValue(&I);
			if (!(sliceItem.isIdentity() && sliceItem.value == &I) && isa<Instruction>(sliceItem.value)) {
				auto curSlices = slices.find(
						{ sliceItem.value, sliceItem.offset });
				if (curSlices == slices.end()) {
					slices[ { sliceItem.value, sliceItem.offset }] = { &I };
				}
			}
			//if (auto *sext = dyn_cast<SExtInst>(&I)) {
			//	auto *bitVector = sext->getOperand(0);
			//	size_t offsetInt = bitVector->getType()->getIntegerBitWidth()
			//			- 1;
			//	auto curSlices = slices.find( { bitVector, offsetInt });
			//	if (curSlices == slices.end()) {
			//		slices[ { bitVector, offsetInt }] = { &I };
			//	}
			//}
		}
	}
	return slices;
}

PreservedAnalyses SlicesMergePass::run(Function &F,
		FunctionAnalysisManager &AM) {
	verifyAfterUpdate(F, nullptr, "got corrupted function");

	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	bool anyChange = false;
	bool firstRun = true;
	for (;;) {
		// run phiShiftPatternRewrite rewriteConcat, mergeConsequentSlices, InstCombinePass, NewGVNPass
		// in loop while something is reduced
		bool change = false;
		DceWorklist::SliceDict slices = findSlices(F);
		auto createSlice =
				[&slices, &F](IRBuilder<> *Builder, Value *bitVec,
						size_t lowBitNo, size_t bitWidth) {
					std::pair<Value*, uint64_t> key(bitVec, lowBitNo);
					auto cur = slices.find(key);
					if (cur == slices.end()) {
						// create a new slice because there is non on this vector
						auto _slice = CreateBitRangeGetConst(Builder, bitVec,
								lowBitNo, bitWidth);
						if (auto _sliceI = dyn_cast<Instruction>(_slice)) {
							assert(isa<Instruction>(bitVec));
							if (IsBitRangeGetInst(_sliceI)) {
								slices[key] = { _sliceI };
							}
						}
						return _slice;
					} else {
						for (Instruction *sliceItem : cur->second) {
							if (auto OpVasI = dyn_cast<Instruction>(
									sliceItem)) {
								assert(
										OpVasI->getParent()
												&& "Check that the replacement is not erased");
								assert(OpVasI->getParent()->getParent() == &F);
							}
							if (sliceItem->getType()->getIntegerBitWidth()
									== bitWidth) {
								// return existing slice with proper lowBitNo, bitWidth
								return (Value*) sliceItem;
							}
						}
						// create new slice because all other slices are different than requested
						auto _slice = CreateBitRangeGetConst(Builder, bitVec,
								lowBitNo, bitWidth);
						if (auto _sliceI = dyn_cast<Instruction>(_slice)) {
							if (IsBitRangeGetInst(_sliceI)) {
								cur->second.push_back(_sliceI);
							}
						}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					if (!isa<GlobalValue>(_slice)) {
						if (auto OpVasI = dyn_cast<Instruction>(_slice)) {
							assert(
									OpVasI->getParent()
											&& "Check that the replacement is not erased");
							assert(OpVasI->getParent()->getParent() == &F);
						}
					}
#endif
					return _slice;
				}
			};

		DceWorklist dce(TLI, &slices);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		dce.assertSlicesConsistency();
#endif
		for (BasicBlock &BB : F) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			dce.assertSlicesConsistency();
#endif
			change |= phiShiftPatternRewrite(BB, createSlice, dce);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			verifyAfterUpdate(F, dce, "phiShiftPatternRewrite corrupted function");
			dce.assertSlicesConsistency();
#endif
		}
		for (BasicBlock &BB : F) {
			for (auto I = BB.begin(); I != BB.end();) {
				if (dce.tryRemoveIfDead(*I, I)) {
					verifyAfterUpdate(F, dce, "DCE received corrupted function");
					dce.runToCompletition(I);
					verifyAfterUpdate(F, dce, "DCE corrupted function");
					change = true;
					continue;
				}

				bool _changed = false;
				if (auto *CallI = dyn_cast<CallInst>(&*I)) {
					if (IsBitConcat(CallI)) {
						verifyAfterUpdate(F, dce, "rewriteConcat received corrupted function");
						_changed = rewriteConcat(CallI, createSlice, dce);
						verifyAfterUpdate(F, dce, "rewriteConcat corrupted function");
					}
				}

				if (!_changed && !slices.empty()) {
					verifyAfterUpdate(F, dce,
							"mergeConsequentSlices received corrupted function");
					_changed |= mergeConsequentSlices(*I, createSlice, dce);
					verifyAfterUpdate(F, dce,
							"mergeConsequentSlices corrupted function");
				}
				_changed |= !dce.empty();
				change |= _changed;
				if (_changed) {
					verifyAfterUpdate(F, dce, "DCE received corrupted function");
					change |= dce.tryRemoveIfDead(*I, I);
					verifyAfterUpdate(F, dce, "DCE corrupted function");
					change = dce.runToCompletition(I);
					verifyAfterUpdate(F, dce, "DCE corrupted function");
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

	verifyAfterUpdate(F, nullptr, "corrupted function");

	if (anyChange) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}
}
}
