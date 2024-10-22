#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>

#include <algorithm>
#include <unordered_set>

#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/GlobalsModRef.h>

#include <hwtHls/llvm/Transforms/bitwidthReducePass/constBitPartsAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitPartsUseAnalysis.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitRewriter.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/bitSliceFlattening.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
// #include <llvm/IR/Verifier.h>
// #define DBG_VERIFY_AFTER_MODIFICATION

namespace hwtHls {

template<typename T>
class ListSet: std::list<T> {
	using list_t = std::list<T>;
	std::unordered_set<T> set;
public:
	ListSet() :
			list_t() {
	}
	bool contains(const T &__x) {
		return set.contains(__x);
	}
	bool empty() const {
		return list_t::empty();
	}

	void push_back(T __x) {
		if (set.contains(__x))
			return;
		list_t::push_back(__x);
		set.insert(__x);
	}

	T& front() {
		return list_t::front();
	}

	void pop_front() {
		auto front = list_t::front();
		set.erase(front);
		list_t::pop_front();
	}
};

static bool runBitwidthReduction(Function &F, TargetLibraryInfo *TLI, bool& CFGChanged) {
//#ifdef DBG_VERIFY_AFTER_MODIFICATION
//	{
//		std::string errTmp = "hwtHls::BitwidthReductionPass received corrupted function ";
//		llvm::raw_string_ostream errSS(errTmp);
//		errSS << F.getName().str();
//		errSS << "\n";
//		if (verifyModule(*F.getParent(), &errSS)) {
//			throw std::runtime_error(errSS.str());
//		}
//	}
//#endif

	ConstBitPartsAnalysisContext A;
	{
		ListSet<Instruction*> Worklist;
		// discover all value constraints
		for (BasicBlock &BB : F) {
			for (Instruction &I : BB) {
				A.visitValue(&I);
				Worklist.push_back(&I);
			}
		}
		A.setShouldResolvePhiValues();
		// transitively propagate constant bits until something changes (def -> use)
		while (!Worklist.empty()) {
			Instruction *I = Worklist.front();
			Worklist.pop_front();
			if (A.updateInstruction(I)) {
				for (auto user : I->users()) {
					if (auto *u = dyn_cast<Instruction>(user)) {
						if (A.constraints.find(u) != A.constraints.end()) {
							Worklist.push_back(u);
						}
					}
				}
			}
		}
	}
	// use the knowledge about bits constant values to resolve truly used bits (use -> def)
	BitPartsUseAnalysisContext AU(A);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (isa<StoreInst>(&I)
					|| (isa<LoadInst>(&I)
							&& dyn_cast<LoadInst>(&I)->isVolatile())
					|| I.isTerminator() || I.isSpecialTerminator()) { // || dyn_cast<BranchInst>(&I) || dyn_cast<SwitchInst>(&I)
				AU.updateUseMaskEntirelyUsed(&I);
			}
		}
	}

	// errs() << "BitwidthReductionPass::run runBitwidthReduction\n";
	// A.dumpConstraints();
	// F.dump();
	// writeCFGToDotFile(F, "before.BitwidthReducePass.dot", nullptr, nullptr);
	bool didModify = false;
	// DCE
	DceWorklist dce(TLI, nullptr);
	BitPartsRewriter rew(A, &dce);
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			rew.rewriteIfRequired(&I);
			didModify = true;
		}
	}

	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *PHI = dyn_cast<PHINode>(&I)) {
				rew.rewritePHINodeArgsIfRequired(PHI);
				didModify = true;
			} else {
				break; // no more PHIs in this block
			}
		}
	}
	CFGChanged = rew.CFGChanged;
	// DCE
	for (BasicBlock &BB : F) {
		for (auto I = BB.begin(); I != BB.end();) {
			if (dce.tryRemoveIfDead(*I, I)) {
				dce.runToCompletition(I);
				didModify = true;
			} else {
				++I;
			}
		}
	}

	// rewriteExtractOnMergeValues + DCE
	IRBuilder<> Builder(&*F.begin()->begin());
	for (BasicBlock &BB : F) {
		for (auto I = BB.begin(); I != BB.end();) {
			if (CallInst *CI = dyn_cast<CallInst>(&*I)) {
				if (IsBitRangeGet(CI)) {
					if (rewriteExtractOnMergeValues(Builder, CI) != CI
							&& dce.tryRemoveIfDead(*I, I)) {
						dce.runToCompletition(I);
						didModify = true;
						continue;
					}
				}
			}
			++I;
		}
	}
// 	writeCFGToDotFile(F, "after.BitwidthReducePass.dot", nullptr, nullptr);
// #ifdef DBG_VERIFY_AFTER_MODIFICATION
// 	{
// 		std::string errTmp = "hwtHls::BitwidthReductionPass corrupted function ";
// 		llvm::raw_string_ostream errSS(errTmp);
// 		errSS << F.getName().str();
// 		errSS << "\n";
// 		if (verifyModule(*F.getParent(), &errSS)) {
// 			throw std::runtime_error(errSS.str());
// 		}
// 	}
// #endif
	return didModify;
}

llvm::PreservedAnalyses BitwidthReductionPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
	bool CFGChanged = false;
	if (!runBitwidthReduction(F, TLI, CFGChanged)) {
		return PreservedAnalyses::all();
	}

	auto PA = PreservedAnalyses();
	PA.preserve<GlobalsAA>();
	if (!CFGChanged) {
		PA.preserveSet<CFGAnalyses>();
	}
	return PA;
}

}
