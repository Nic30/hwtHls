/*
 * This whole file is mostly original SimplifyCFG with just patch for switch instr merge checks.
 * This is required in order to successfully translate large SwitchInst to load from constant array
 * */
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/TargetFolder.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/Support/Debug.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_normalizeLookupTableIndex.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_phiToLogicalExpr.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_rewriteMaskPatternsFromCFGToData.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamReadMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_aggresiveStoreSink.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_mergePredecessorsStore.h>
#include <hwtHls/llvm/Transforms/BitcountMergePass.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>


#include <map>
#include "HwtHlsSimplifyCFG.h"

//#define DBG_VERIFY_AFTER_EVERY_MODIFICATION

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

#define DEBUG_TYPE "simplifycfg2"

// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

using namespace llvm;
namespace hwtHls {

template<typename T>
cl::opt<T>& getLlvmOption(llvm::StringRef name) {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto opt = Map.find(name);
	assert(opt != Map.end());
	return *dynamic_cast<cl::opt<T>*>(opt->second);
}

// [copied] copied from llvm because of SimplifyCFG private Options which can not be accessed through inheritance
// Command-line settings override compile-time settings.
static void applyCommandLineOverridesToOptions(HwtHlsSimplifyCFGOptions &Options) {
	auto &UserBonusInstThreshold = getLlvmOption<unsigned>(
			"bonus-inst-threshold");
	auto &UserForwardSwitchCond = getLlvmOption<bool>("forward-switch-cond");
	auto &UserSwitchRangeToICmp = getLlvmOption<bool>("switch-range-to-icmp");
	auto &UserSwitchToLookup = getLlvmOption<bool>("switch-to-lookup");
	auto &UserKeepLoops = getLlvmOption<bool>("keep-loops");
	auto &UserHoistCommonInsts = getLlvmOption<bool>("hoist-common-insts");
	auto &UserSinkCommonInsts = getLlvmOption<bool>("sink-common-insts");
	auto &UserHoistCheapInsts = getLlvmOption<bool>("hoist-cheap-insts");
	//auto &UserSinkCheapInsts = getLlvmOption<bool>("sink-cheap-insts");
	if (UserBonusInstThreshold.getNumOccurrences())
		Options.BonusInstThreshold = UserBonusInstThreshold;
	if (UserForwardSwitchCond.getNumOccurrences())
		Options.ForwardSwitchCondToPhi = UserForwardSwitchCond;
	if (UserSwitchRangeToICmp.getNumOccurrences())
		Options.ConvertSwitchRangeToICmp = UserSwitchRangeToICmp;
	if (UserSwitchToLookup.getNumOccurrences())
		Options.ConvertSwitchToLookupTable = UserSwitchToLookup;
	if (UserKeepLoops.getNumOccurrences())
		Options.NeedCanonicalLoop = UserKeepLoops;
	if (UserHoistCommonInsts.getNumOccurrences())
		Options.HoistCommonInsts = UserHoistCommonInsts;
	if (UserSinkCommonInsts.getNumOccurrences())
		Options.SinkCommonInsts = UserSinkCommonInsts;
	if (UserHoistCheapInsts.getNumOccurrences())
		Options.HoistCheapInsts = UserHoistCheapInsts;
	//if (UserSinkCheapInsts.getNumOccurrences())
	//	Options.SinkCheapInsts = UserSinkCheapInsts;
}

HwtHlsSimplifyCFGPass::HwtHlsSimplifyCFGPass() :
		SimplifyCFGPass() {
	applyCommandLineOverridesToOptions(Options);
}

HwtHlsSimplifyCFGPass::HwtHlsSimplifyCFGPass(const HwtHlsSimplifyCFGOptions &Opts) :
		SimplifyCFGPass(Opts), Options(Opts) {
	applyCommandLineOverridesToOptions(Options);
}
template<typename PassTy>
bool runSubpass(PassInstrumentation &PI, Function &F,
		FunctionAnalysisManager &FAM, PassTy &Pass) {
	// based on ModuleToFunctionPassAdaptor::run
	// Check the PassInstrumentation's BeforePass callbacks before running the
	// pass, skip its execution completely if asked to (callback returns
	// false).
	if (!PI.runBeforePass<Function>(Pass, F))
		return false;

	PreservedAnalyses PassPA = Pass.run(F, FAM);

	// We know that the function pass couldn't have invalidated any other
	// function's analyses (that's the contract of a function pass), so
	// directly handle the function analysis manager's invalidation here.
	FAM.invalidate(F, PassPA);

	PI.runAfterPass(Pass, F, PassPA);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(F, &errs()));
#endif
	return !PassPA.areAllPreserved();
}

// run SimplifyCFGPass::run, SimplifyCFGOpt2 and SimplifyCFGPass2_normalizeLookupTableIndex
llvm::PreservedAnalyses HwtHlsSimplifyCFGPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	size_t itCntr = 0;
	Options.AC = &AM.getResult<AssumptionAnalysis>(F);
	auto &AC = *Options.AC;
	DominatorTree *DT = nullptr;
	bool RequireAndPreserveDomTree = true;

	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DL = F.getParent()->getDataLayout();
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto _LlvmHoistCommonSkipLimit = Map.find(
			"simplifycfg-hoist-common-skip-limit");
	assert(_LlvmHoistCommonSkipLimit != Map.end());
	unsigned LlvmHoistCommonSkipLimit =
			dynamic_cast<cl::opt<unsigned>*>(_LlvmHoistCommonSkipLimit->second)->getValue();
	bool changed = false;
	IRBuilder<TargetFolder, IRBuilderCallbackInserter> Builder(F.getContext(),
			TargetFolder(DL), IRBuilderCallbackInserter([&AC](Instruction *I) {
				if (auto *Assume = dyn_cast<AssumeInst>(I))
					AC.registerAssumption(Assume);
			}));

	auto PA_all = PreservedAnalyses::all();
	// Request PassInstrumentation from analysis manager, will use it to run
	// instrumenting callbacks for the passes later.
	PassInstrumentation PI = AM.getResult<PassInstrumentationAnalysis>(F);

	for (;;) {
		// run initial cse and expression simplification to get expression into normal form
		// to maximize probability that it will be possible to match condition implications
		// and other condition/phi patterns
		EarlyCSEPass ecsePass;
		bool exprChanged = runSubpass(PI, F, AM, ecsePass);
		HwtHlsInstCombinePass hicPass(HwtHlsInstCombinePassOptions(/*extractBitcounts*/false));
		exprChanged |= runSubpass(PI, F, AM, hicPass);
		//exprChanged |= !InstCombinePass().run(F, AM).areAllPreserved();
		changed |= exprChanged;

		if (RequireAndPreserveDomTree) {
			DT = &AM.getResult<DominatorTreeAnalysis>(F);
		}
		assert(Options.AC == &AM.getResult<AssumptionAnalysis>(F));
		DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
		SimplifyCFGOpt2 opt(&DTU, DL, TTI, Options, LlvmHoistCommonSkipLimit);
		bool _changed0 = false;
		for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
			BasicBlock &BB = *BBIt++;
			assert(
					!DTU.isBBPendingDeletion(&BB)
							&& "Should not end up trying to simplify blocks marked for removal.");
			// Make sure that the advanced iterator does not point at the blocks
			// that are marked for removal, skip over all such blocks.
			while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
				++BBIt;
			assert(&BB && BB.getParent() && "Block not embedded in function!");
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed0 |= opt.run(&BB);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
				++BBIt;
			DTU.flush(); // (required because otherwise blocks are removed before update is applied)
			if (DTU.isBBPendingDeletion(&BB))
				continue;

			_changed0 |= HwtHlsSimplifyCFGPass_normalizeLookupTableIndex(BB);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed0 |= HwtHlsSimplifyCFGPass_rewriteMaskPatternsFromCFGToData(DTU,
					BB);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));

#endif
		}
		DTU.flush();

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(DT->verify());
		assert(!verifyFunction(F, &errs()));
#endif
		changed |= _changed0;
		bool _changed1 = false;
		auto SQ = getBestSimplifyQuery(AM, F); // :attention: this asks for DT
		for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
			//auto _PA = PreservedAnalyses::all();
			////_PA.abandon<DominatorTreeAnalysis>();
			//AM.invalidate(F, _PA);
			//DT = &AM.getResult<DominatorTreeAnalysis>(F);
			//auto _DTU = DomTreeUpdater(DT, DomTreeUpdater::UpdateStrategy::Lazy);

			// continue rewriting this block while it is updated
			// writeCFGToDotFile(F, "tmp/SimplifyCFG2.before.dot", AM);
			if (HwtHlsSimplifyCFGPass_aggresiveStoreSink(DTU, *BBIt)) {
				// writeCFGToDotFile(F, "tmp/SimplifyCFG2.after.dot", AM);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));

#endif
				_changed1 = true;
			} else if (HwtHlsSimplifyCFGPass_mergePredecessorsStore(DTU, *BBIt)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));

#endif
				_changed1 = true;
			} else if (HwtHlsSimplifyCFGPass_phiToLogicalExpr(Builder, DTU, DL, &AC,
					*BBIt)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));

#endif
				_changed1 = true;
			} else if (HwtHlsSimplifyCFGPass_streamWriteMerge(Builder, DTU, *BBIt,
					SQ)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));

#endif
				_changed1 = true;
			} else if (HwtHlsSimplifyCFGPass_streamReadMerge(Builder, DTU, *BBIt,
					SQ)) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				assert(!verifyFunction(F, &errs()));

#endif
				_changed1 = true;
			} else {
				BBIt++;
			}
		}
		changed |= _changed1;
		DTU.flush();
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		DT->verify();
		assert(!verifyFunction(F, &errs()));
#endif


		// run original SimplifyCFGPass::run
		bool _changed2 = false;
		SimplifyCFGPass origSimplifyCfg(Options);
		PreservedAnalyses _PA = PreservedAnalyses::all();
		_PA.abandon<DominatorTreeAnalysis>();
		AM.invalidate(F, _PA);
		bool changed_origSimplifyCfg = runSubpass(PI, F, AM, origSimplifyCfg);
		if (!_changed0 && !_changed1 && !changed_origSimplifyCfg) {
			if (itCntr > 0)
				break;
		} else {
			_changed2 = true;
		}
		changed |= _changed2;

		if (!_changed0 && !_changed1 && !_changed2) {
			HwtHlsInstCombinePass hicPass(
					HwtHlsInstCombinePassOptions(/*extractBitcounts*/true));
			BitcountMergePass bmPass;
			if (runSubpass(PI, F, AM, hicPass)) {
				runSubpass(PI, F, AM, bmPass);
				changed = true;
			} else {
				if (runSubpass(PI, F, AM, bmPass)) {
					changed = true;
				} else {
					break;
				}

			}
		}
		itCntr++;
		assert(itCntr < 1000 && "SimplifyCFGPass2 did not converge");
	}

	if (changed) {
		PreservedAnalyses PA;
		if (RequireAndPreserveDomTree)
			PA.preserve<DominatorTreeAnalysis>();
		return PA;
	}
	return PreservedAnalyses::all();
}

}
