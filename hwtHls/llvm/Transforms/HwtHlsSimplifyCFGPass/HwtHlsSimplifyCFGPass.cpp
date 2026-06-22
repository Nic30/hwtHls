#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass.h>

#include <llvm/IR/Analysis.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/InstSimplifyFolder.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/TargetFolder.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/IR/PassInstrumentation.h>
#include <llvm/Support/Debug.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_hoistHoistableAssumes.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_memHoistToNewBB.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_memSinkToNewBB.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_normalizeLookupTableIndex.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_phiToLogicalExpr.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_rewriteMaskPatternsFromCFGToData.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamReadMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_aggresiveStoreSink.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_mergePredecessorsStore.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_speculatePredecessor.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_storeHoist.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks.h>
#include <hwtHls/llvm/Transforms/BitcountMergePass.h>
#include <hwtHls/llvm/Transforms/RomExtractPass.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;

namespace hwtHls {
static llvm::cl::opt<size_t> OPT_ITERATION_COUNT(
    "hwthls-simplifycfg-ITERATION-LIMIT", cl::Hidden, cl::init(1000),
	llvm::cl::desc("The maximum allowed number of internal iterations in HwtHlsSimplifyCFG pass (default = 1000)"));
#define DEFINE_LLVM_BOOL_OPTION(name) \
  static llvm::cl::opt<bool> name("hwthls-simplifycfg-" #name, cl::Hidden, cl::init(true), llvm::cl::desc("(default = true)"))
DEFINE_LLVM_BOOL_OPTION(SwitchReduceRange);
DEFINE_LLVM_BOOL_OPTION(HoistHoistableAssumes);
DEFINE_LLVM_BOOL_OPTION(MemHoistToNewBB);
DEFINE_LLVM_BOOL_OPTION(MemSinkToNewBB);
DEFINE_LLVM_BOOL_OPTION(NormalizeLookupTableIndex);
DEFINE_LLVM_BOOL_OPTION(RewriteMaskPatternsFromCFGToData);
DEFINE_LLVM_BOOL_OPTION(StoreHoist);
DEFINE_LLVM_BOOL_OPTION(AggresiveStoreSink);
DEFINE_LLVM_BOOL_OPTION(MergePredecessorsStore);
DEFINE_LLVM_BOOL_OPTION(PhiToLogicalExpr);
DEFINE_LLVM_BOOL_OPTION(UnswitchCheapManyPredManySuccBB);
DEFINE_LLVM_BOOL_OPTION(UnswitchComplementarySequentialBlocks);
DEFINE_LLVM_BOOL_OPTION(SpeculatePredecessor);
DEFINE_LLVM_BOOL_OPTION(StreamWriteMerge);
DEFINE_LLVM_BOOL_OPTION(StreamReadMerge);
DEFINE_LLVM_BOOL_OPTION(SwitchToSelectOrRomLoad);
DEFINE_LLVM_BOOL_OPTION(SwitchSuccClusterReduceFewExit);
DEFINE_LLVM_BOOL_OPTION(NormalizeBrCond);
DEFINE_LLVM_BOOL_OPTION(ConstantFoldTerminator);
DEFINE_LLVM_BOOL_OPTION(EliminateDuplicatePHINodes);
DEFINE_LLVM_BOOL_OPTION(EemoveUndefIntroducingPredecessor);
DEFINE_LLVM_BOOL_OPTION(MergeBlockIntoPredecessor);
DEFINE_LLVM_BOOL_OPTION(RunEarlyCSEPass);
DEFINE_LLVM_BOOL_OPTION(RunRomExtractPass);
DEFINE_LLVM_BOOL_OPTION(RunHwtHlsInstCombinePass);
DEFINE_LLVM_BOOL_OPTION(RunTrivialSimplifyCFGPass);
DEFINE_LLVM_BOOL_OPTION(RunSimplifyCFGPass);
DEFINE_LLVM_BOOL_OPTION(RunBitcountMergePass);
#undef DEFINE_LLVM_BOOL_OPTION

template<typename T>
cl::opt<T>& getLlvmOption(llvm::StringRef name) {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto opt = Map.find(name);
	assert(opt != Map.end());
	return *dynamic_cast<cl::opt<T>*>(opt->second);
}

// [copied] copied from llvm because of SimplifyCFG private Options which can not be accessed through inheritance
// Command-line settings override compile-time settings.
static void applyCommandLineOverridesToOptions(
		HwtHlsSimplifyCFGOptions &Options) {
	auto &BonusInstThreshold = getLlvmOption<unsigned>(
			"bonus-inst-threshold");
	auto &ForwardSwitchCondToPhi = getLlvmOption<bool>("forward-switch-cond");
	auto &ConvertSwitchRangeToICmp = getLlvmOption<bool>("switch-range-to-icmp");
	auto &ConvertSwitchToLookupTable = getLlvmOption<bool>("switch-to-lookup");
	auto &NeedCanonicalLoop = getLlvmOption<bool>("keep-loops");
	auto &HoistCommonInsts = getLlvmOption<bool>("hoist-common-insts");
	auto &SinkCommonInsts = getLlvmOption<bool>("sink-common-insts");
	auto &HoistCheapInsts = getLlvmOption<bool>("hoist-cheap-insts");
#define FORWARD_LLVM_OPTION(option_name) \
  if (option_name.getNumOccurrences()) \
    Options.option_name = option_name;
	//auto &UserSinkCheapInsts = getLlvmOption<bool>("sink-cheap-insts");
	FORWARD_LLVM_OPTION(BonusInstThreshold);
	FORWARD_LLVM_OPTION(ForwardSwitchCondToPhi);
	FORWARD_LLVM_OPTION(ConvertSwitchRangeToICmp);
	FORWARD_LLVM_OPTION(ConvertSwitchToLookupTable);
	FORWARD_LLVM_OPTION(NeedCanonicalLoop);
	FORWARD_LLVM_OPTION(HoistCommonInsts);
	FORWARD_LLVM_OPTION(SinkCommonInsts);
	FORWARD_LLVM_OPTION(HoistCheapInsts);
	  if (OPT_ITERATION_COUNT.getNumOccurrences()) \
	    Options.ITERATION_LIMIT = OPT_ITERATION_COUNT;
	//if (UserSinkCheapInsts.getNumOccurrences())
	//	Options.SinkCheapInsts = UserSinkCheapInsts;
	FORWARD_LLVM_OPTION(SwitchReduceRange);
	FORWARD_LLVM_OPTION(HoistHoistableAssumes);
	// FORWARD_LLVM_OPTION(MemSinkToNewBB);
	FORWARD_LLVM_OPTION(NormalizeLookupTableIndex);
	FORWARD_LLVM_OPTION(RewriteMaskPatternsFromCFGToData);
	FORWARD_LLVM_OPTION(StoreHoist);
	FORWARD_LLVM_OPTION(AggresiveStoreSink);
	FORWARD_LLVM_OPTION(MergePredecessorsStore);
	FORWARD_LLVM_OPTION(PhiToLogicalExpr);
	FORWARD_LLVM_OPTION(UnswitchCheapManyPredManySuccBB);
	FORWARD_LLVM_OPTION(UnswitchComplementarySequentialBlocks);
	FORWARD_LLVM_OPTION(SpeculatePredecessor);
	FORWARD_LLVM_OPTION(StreamWriteMerge);
	FORWARD_LLVM_OPTION(StreamReadMerge);
	FORWARD_LLVM_OPTION(SwitchToSelectOrRomLoad);
	FORWARD_LLVM_OPTION(SwitchSuccClusterReduceFewExit);
	FORWARD_LLVM_OPTION(NormalizeBrCond);
	FORWARD_LLVM_OPTION(ConstantFoldTerminator);
	FORWARD_LLVM_OPTION(EliminateDuplicatePHINodes);
	FORWARD_LLVM_OPTION(EemoveUndefIntroducingPredecessor);
	FORWARD_LLVM_OPTION(MergeBlockIntoPredecessor);
	FORWARD_LLVM_OPTION(RunEarlyCSEPass);
	FORWARD_LLVM_OPTION(RunRomExtractPass);
	FORWARD_LLVM_OPTION(RunHwtHlsInstCombinePass);
	FORWARD_LLVM_OPTION(RunTrivialSimplifyCFGPass);
	FORWARD_LLVM_OPTION(RunSimplifyCFGPass);
	FORWARD_LLVM_OPTION(RunBitcountMergePass);
#undef FORWARD_LLVM_OPTION
}

HwtHlsSimplifyCFGPass::HwtHlsSimplifyCFGPass() :
		SimplifyCFGPass() {
	applyCommandLineOverridesToOptions(Options);
}

// [todo]
// void HwtHlsSimplifyCFGPass::printPipeline(
//     raw_ostream &OS, function_ref<StringRef(StringRef)> MapClassName2PassName)

HwtHlsSimplifyCFGPass::HwtHlsSimplifyCFGPass(
		const HwtHlsSimplifyCFGOptions &Opts) :
		SimplifyCFGPass(Opts), Options(Opts) {
	applyCommandLineOverridesToOptions(Options);
}

template<typename PassTy>
bool runSubpass(PassInstrumentation &PI, Function &F,
		FunctionAnalysisManager &FAM, PassTy &Pass) {
	// based on ModuleToFunctionPassAdaptor::run
	// :attention: this has the problem that if there is some check in
	//  afterPass/beforePass that check potentially fails in sub pass instead of this pass

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

void HwtHlsSimplifyCFGPass::onChangeCallback(const std::string & ruleName, llvm::Function & F) {
	if (Options._dbgIrCfgSimplifyChangeCallbackFn) {
		(*Options._dbgIrCfgSimplifyChangeCallbackFn)(ruleName, F);
	}
}

void HwtHlsSimplifyCFGPass::onChangeCallbackIC(const std::string & ruleName, llvm::Function & F) {
	if (Options._dbgIrInstrCombineChangeCallbackFn) {
		(*Options._dbgIrInstrCombineChangeCallbackFn)(ruleName, F);
	}
}

bool HwtHlsSimplifyCFGPass::runOpt0(Function &F, DomTreeUpdater &DTU,
		SimplifyCFGOpt2 &opt, bool &exprChanged) {
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
		// the error will appear there only if the input was broken or some check is missing after change
		// onChangeCallbackIC("HwtHlsSimplifyCFGPass::runOpt0 - entry", F);
				
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
		if (Options.HoistHoistableAssumes &&
			HwtHlsSimplifyCFGPass_hoistHoistableAssumes(BB)) {
			onChangeCallbackIC("HwtHlsSimplifyCFGPass_hoistHoistableAssumes",
							   F);
			exprChanged = true;
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
		}
		_changed0 |= opt.run(&BB, exprChanged);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(F, &errs()));
#endif
		while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
			++BBIt;
		if (DTU.isBBPendingDeletion(&BB))
			continue;
		DTU.flush(); // (required because otherwise blocks are removed before update is applied)

		if (Options.NormalizeLookupTableIndex
				&& HwtHlsSimplifyCFGPass_normalizeLookupTableIndex(BB)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_normalizeLookupTableIndex", F);
			_changed0 = true;
			#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
			#endif
		}
		if (Options.RewriteMaskPatternsFromCFGToData
				&& HwtHlsSimplifyCFGPass_rewriteMaskPatternsFromCFGToData(DTU,
						BB)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_rewriteMaskPatternsFromCFGToData", F);
			_changed0 = true; 
			#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
					assert(!verifyFunction(F, &errs()));
			#endif
		}
	}
	return _changed0;
}

bool HwtHlsSimplifyCFGPass::runOpt1(llvm::FunctionAnalysisManager &AM,
		IRBuilderBase &Builder, const DataLayout &DL, AssumptionCache &AC,
		Function &F, DomTreeUpdater &DTU, SimplifyCFGOpt2 &opt,
		bool &exprChanged) {
	auto SQ = getBestSimplifyQuery(AM, F); // :attention: this asks for DT
	bool _changed1 = false;
	for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
		assert(BBIt->getParent());
		//auto _PA = PreservedAnalyses::all();
		////_PA.abandon<DominatorTreeAnalysis>();
		//AM.invalidate(F, _PA);
		//DT = &AM.getResult<DominatorTreeAnalysis>(F);
		//auto _DTU = DomTreeUpdater(DT, DomTreeUpdater::UpdateStrategy::Lazy);

		// continue rewriting this block while it is updated
		DTU.flush();
		// writeCFGToDotFile(F, "tmp/SimplifyCFG2.before.dot", AM, false, true);
		// errs() << F << "\n";
		// the error will appear there only if the input was broken or some check is missing after change
		// onChangeCallbackIC("HwtHlsSimplifyCFGPass::runOpt1 - entry", F);
		if (Options.StoreHoist && HwtHlsSimplifyCFGPass_storeHoist(*BBIt)) {
			onChangeCallbackIC("HwtHlsSimplifyCFGPass_storeHoist", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			// DTU.flush();
			// writeCFGToDotFile(F, "tmp/HwtHlsSimplifyCFGPass_storeHoist.after.dot", AM);
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.MemHoistToNewBB && HwtHlsSimplifyCFGPass_memHoistToNewBB(DTU, *BBIt)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_memHoistToNewBB", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			DTU.flush();
			// writeCFGToDotFile(F, "tmp/HwtHlsSimplifyCFGPass_memHoistToNewBB.after.dot", AM);
			assert(!verifyFunction(F, &errs()));
#endif
					_changed1 = true;
		} else if (Options.AggresiveStoreSink
				&& HwtHlsSimplifyCFGPass_aggresiveStoreSink(DTU, *BBIt)) {
			// writeCFGToDotFile(F, "tmp/SimplifyCFG2.after.dot", AM);
			onChangeCallback("HwtHlsSimplifyCFGPass_aggresiveStoreSink", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.MergePredecessorsStore
				&& HwtHlsSimplifyCFGPass_mergePredecessorsStore(DTU, *BBIt)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_mergePredecessorsStore", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			// DTU.flush();
			// writeCFGToDotFile(F, "tmp/HwtHlsSimplifyCFGPass_mergePredecessorsStore.after.dot", AM);
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.MemSinkToNewBB
					&& HwtHlsSimplifyCFGPass_memSinkToNewBB(DTU, *BBIt)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_memSinkToNewBB", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
					_changed1 = true;
		} else if (Options.PhiToLogicalExpr
				&& HwtHlsSimplifyCFGPass_phiToLogicalExpr(Builder, DTU, DL, &AC,
						*BBIt, exprChanged)) {
			onChangeCallbackIC("HwtHlsSimplifyCFGPass_phiToLogicalExpr", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.UnswitchComplementarySequentialBlocks
				&& HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks(
						Builder, DTU, *BBIt, exprChanged)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.UnswitchCheapManyPredManySuccBB &&
				   BBIt->hasNPredecessorsOrMore(2) &&
				   BBIt->getTerminator()->getNumSuccessors() >= 2 &&
				   HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB(
					   Builder, DTU, *BBIt, exprChanged)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
					_changed1 = true;
		} else if (Options.SwitchSuccClusterReduceFewExit &&
				   isa<SwitchInst>(BBIt->getTerminator()) &&
				   HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
					   Builder, DTU, *cast<SwitchInst>(BBIt->getTerminator()),
					   exprChanged)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			DTU.flush();
			// writeCFGToDotFile(F, "tmp/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.after.dot", AM);
			assert(!verifyFunction(F, &errs()));
			auto& DT = DTU.getDomTree();
			assert(DT.verify());
#endif
			_changed1 = true;

		} else if (Options.SpeculatePredecessor &&
				   HwtHlsSimplifyCFGPass_speculatePredecessor(DTU, *BBIt)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_speculatePredecessor", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.StreamWriteMerge &&
				   HwtHlsSimplifyCFGPass_streamWriteMerge(Builder, DTU, *BBIt,
														  SQ)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_streamWriteMerge", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else if (Options.StreamReadMerge &&
				   HwtHlsSimplifyCFGPass_streamReadMerge(Builder, DTU, *BBIt,
														 SQ)) {
			onChangeCallback("HwtHlsSimplifyCFGPass_streamReadMerge", F);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(!verifyFunction(F, &errs()));
#endif
			_changed1 = true;
		} else {
			BBIt++;
		}
	}
	return _changed1;
}

// run SimplifyCFGPass::run, SimplifyCFGOpt2 and SimplifyCFGPass2_normalizeLookupTableIndex
llvm::PreservedAnalyses HwtHlsSimplifyCFGPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {

	Options.AC = &AM.getResult<AssumptionAnalysis>(F);
	auto &AC = *Options.AC;
	DominatorTree *DT = nullptr;
	bool RequireAndPreserveDomTree = true;

	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DL = F.getDataLayout();
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto _LlvmHoistCommonSkipLimit = Map.find(
			"simplifycfg-hoist-common-skip-limit");
	assert(_LlvmHoistCommonSkipLimit != Map.end());
	unsigned LlvmHoistCommonSkipLimit =
			dynamic_cast<cl::opt<unsigned>*>(_LlvmHoistCommonSkipLimit->second)->getValue();
	bool changed = false;
	// InstSimplifyFolder, TargetFolder
	IRBuilder<TargetFolder, IRBuilderCallbackInserter> Builder(F.getContext(),
			TargetFolder(DL), IRBuilderCallbackInserter([&AC](Instruction *I) {
				using namespace PatternMatch;
				if (auto *Assume = dyn_cast<AssumeInst>(I)) {
					AC.registerAssumption(Assume);
				}
			}));

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(F, &errs()));
#endif
	auto PA_all = PreservedAnalyses::all();
	// Request PassInstrumentation from analysis manager, will use it to run
	// instrumenting callbacks for the passes later.
	PassInstrumentation PI = AM.getResult<PassInstrumentationAnalysis>(F);

	size_t itCntr = 0;
	size_t lastIterationWithCfgChange = 0;
	for (;;) {
		// run initial cse and expression simplification to get expression into normal form
		// to maximize probability that it will be possible to match condition implications
		// and other condition/phi patterns
		bool exprChanged = false;
		if (Options.RunEarlyCSEPass) {
			EarlyCSEPass ecsePass;
			if (runSubpass(PI, F, AM, ecsePass)) {
				onChangeCallbackIC("HwtHlsSimplifyCFGPass - EarlyCSEPass", F);
			}
		}
		if (Options.RunRomExtractPass) {
			RomExtractPass romExtractPass; // :note: executed before HwtHlsInstCombinePass because HwtHlsInstCombinePass may lower SelectInst to concat
			if (runSubpass(PI, F, AM, romExtractPass)) {
				onChangeCallbackIC("HwtHlsSimplifyCFGPass - RomExtractPass", F);
				exprChanged = true;
			}
		}
		if (Options.RunHwtHlsInstCombinePass) {
			// can not perform vectorization of function calls and alike during cfg optimizations
			// because in original code there is always phi/select to select from sequence of such instructions
			// if we perform this opt before cfg is simplified there may be multiple such phi/select instructions
			// which would result in duplication of vectorized instruction (which is considered costly)
			HwtHlsInstCombinePass hicPass(
					HwtHlsInstCombinePassOptions(/*extractBitcounts*/false)
					.setMergeMergableFunctionCalls(false)
					.setdbgIrInstrCombineChangeCallbackFn(Options._dbgIrInstrCombineChangeCallbackFn));
			exprChanged |= runSubpass(PI, F, AM, hicPass);
		}
		//exprChanged |= !InstCombinePass().run(F, AM).areAllPreserved();
		changed |= exprChanged;

		if (RequireAndPreserveDomTree) {
			DT = &AM.getResult<DominatorTreeAnalysis>(F);
		}
		bool _changed0 = false; // true if runOpt0 changed F in following for
		bool _changed1 = false; // true if runOpt1 changed F in following for
		for (;;) {
			assert(Options.AC == &AM.getResult<AssumptionAnalysis>(F));
			DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
			auto PA = PreservedAnalyses::all();
			PA.abandon<LoopAnalysis>();
			PA.abandon<BlockFrequencyAnalysis>();
			PA.abandon<BranchProbabilityAnalysis>();	
			AM.invalidate(F, PA);

			SimplifyCFGOpt2 opt(&DTU, DL, TTI, Options,
					LlvmHoistCommonSkipLimit);
			opt._dbgIrCfgSimplifyChangeCallbackFn =
				Options._dbgIrCfgSimplifyChangeCallbackFn;
			opt._dbgIrInstrCombineChangeCallbackFn =
				Options._dbgIrInstrCombineChangeCallbackFn;
			bool __changed0 = false;
			// try {
			while (runOpt0(F, DTU, opt, exprChanged)) {
				__changed0 = true;
				itCntr++;
				assert(
						itCntr < Options.ITERATION_LIMIT
								&& "SimplifyCFGPass2 did not converge");

			}
			// } catch (std::runtime_error & e) {
			// 	// [dbg]
			// 	writeCFGToDotFile(F, "tmp/SimplifyCFG2.after.dot", AM);
			// 	assert(false && "[dbg]");
			// 	throw e;
			// }
			_changed0 |= __changed0;
			changed |= __changed0;

			DTU.flush();

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			assert(DT->verify());
			assert(!verifyFunction(F, &errs()));
#endif
			bool __changed1 = false;
			while (runOpt1(AM, Builder, DL, AC, F, DTU, opt, exprChanged)) {
				__changed1 = true;
				itCntr++;
				assert(
						itCntr < Options.ITERATION_LIMIT
								&& "SimplifyCFGPass2 did not converge");

			}
			_changed1 |= __changed1;
			changed |= __changed1;

			DTU.flush();
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
			DT->verify();
			assert(!verifyFunction(F, &errs()));
#endif
			bool changed_trivialSimplifyCfg = false;
			if (Options.RunTrivialSimplifyCFGPass) {
				TrivialSimplifyCFGPass trivialSimplifyCfg(true, false);
				changed_trivialSimplifyCfg = runSubpass(PI, F, AM,
						trivialSimplifyCfg);
				if (changed_trivialSimplifyCfg) {
					onChangeCallback("HwtHlsSimplifyCFGPass - TrivialSimplifyCFGPass",
									   F);
				}
				changed |= changed_trivialSimplifyCfg;
			}
			if (!__changed0 && !__changed1 && !changed_trivialSimplifyCfg)
				break;
			itCntr++;
			assert(
					itCntr < Options.ITERATION_LIMIT
							&& "SimplifyCFGPass2 did not converge");

		}
		// run original SimplifyCFGPass::run
		bool _changed2 = false;
		bool changed_origSimplifyCfg = false;
		if (Options.RunSimplifyCFGPass) {
			SimplifyCFGPass origSimplifyCfg(Options); // :attention: does not preserve loop metadata
			PreservedAnalyses _PA = PreservedAnalyses::all();
			_PA.abandon<DominatorTreeAnalysis>();
			AM.invalidate(F, _PA);
			changed_origSimplifyCfg = runSubpass(PI, F, AM, origSimplifyCfg);
			if (changed_origSimplifyCfg) {
				onChangeCallback("HwtHlsSimplifyCFGPass - llvm::SimplifyCFGPass",
								   F);
			}
		}
		//LoopFuseWithPrequelPass fuseWithPrequel;
		//bool changed_fuseWithPrequel = runSubpass(PI, F, AM, fuseWithPrequel);
		bool changed_fuseWithPrequel = false;
		if (!_changed0 && !_changed1 && !changed_origSimplifyCfg
				&& !changed_fuseWithPrequel) {
			if (itCntr > 0)
				break;
		} else {
			_changed2 = true;
		}
		changed |= _changed2;

		if (!_changed0 && !_changed1 && !_changed2) {
			if (lastIterationWithCfgChange + 1 < itCntr)
				break; // last 2 iterations did not change the CFG
			HwtHlsInstCombinePass hicPass(
				HwtHlsInstCombinePassOptions(/*extractBitcounts*/ true)
					.setdbgIrInstrCombineChangeCallbackFn(
						Options._dbgIrInstrCombineChangeCallbackFn));
			BitcountMergePass bmPass;
			auto blockCnt = F.size();
			if (Options.RunHwtHlsInstCombinePass && runSubpass(PI, F, AM, hicPass)) {
				assert(blockCnt == F.size());
				runSubpass(PI, F, AM, bmPass);
				assert(blockCnt == F.size());
				changed = true;
			} else if (Options.RunBitcountMergePass && runSubpass(PI, F, AM, bmPass)) {
				onChangeCallbackIC("HwtHlsSimplifyCFGPass -BitcountMergePass",
								   F);
				changed = true;
			} else {
				break;
			}
		} else {
			lastIterationWithCfgChange = itCntr;
		}
		itCntr++;
		assert(itCntr < Options.ITERATION_LIMIT && "HwtHlsSimplifyCFGPass did not converge");
	}

	if (changed) {
		if (!Options.SwitchReduceRange) {
			for (auto &BB : F) {
				if (auto SW = dyn_cast<SwitchInst>(BB.getTerminator()))
					if (HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo(*SW)) {
						onChangeCallbackIC("HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo",
										   F);
					}
			}
		}
		PreservedAnalyses PA;
		if (RequireAndPreserveDomTree)
			PA.preserve<DominatorTreeAnalysis>();
		return PA;
	}
	return PreservedAnalyses::all();
}

}
