/*
 * This whole file is mostly original SimplifyCFG with just patch for switch instr merge checks.
 * This is required in order to successfully translate large SwitchInst to load from constant array
 * */
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/Support/Debug.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_normalizeLookupTableIndex.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_aggresiveStoreSink.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_mergePredecessorsStore.h>


#include <map>

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
static void applyCommandLineOverridesToOptions(SimplifyCFG2Options &Options) {
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

SimplifyCFG2Pass::SimplifyCFG2Pass() :
		SimplifyCFGPass() {
	applyCommandLineOverridesToOptions(Options);
}

SimplifyCFG2Pass::SimplifyCFG2Pass(const SimplifyCFG2Options &Opts) :
		SimplifyCFGPass(Opts), Options(Opts) {
	applyCommandLineOverridesToOptions(Options);
}


// run SimplifyCFGPass::run, SimplifyCFGOpt2 and SimplifyCFGPass2_normalizeLookupTableIndex
llvm::PreservedAnalyses SimplifyCFG2Pass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	size_t itCntr = 0;
	Options.AC = &AM.getResult<AssumptionAnalysis>(F);
	DominatorTree *DT = nullptr;
	RequireAndPreserveDomTree = true;

	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DL = F.getParent()->getDataLayout();
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto _LlvmHoistCommonSkipLimit = Map.find(
			"simplifycfg-hoist-common-skip-limit");
	assert(_LlvmHoistCommonSkipLimit != Map.end());
	unsigned LlvmHoistCommonSkipLimit =
			dynamic_cast<cl::opt<unsigned>*>(_LlvmHoistCommonSkipLimit->second)->getValue();
	llvm::PreservedAnalyses FirstPA;

	bool changed = false;
	for (;;) {
		auto PA = SimplifyCFGPass::run(F, AM);
		if (itCntr == 0)
			FirstPA = PA;

		if (PA.areAllPreserved()) {
			if (itCntr > 0)
				break;
		} else {
			changed = true;
		}
		if (RequireAndPreserveDomTree) {
			DT = &AM.getResult<DominatorTreeAnalysis>(F);
		}
		DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
		SimplifyCFGOpt2 opt(&DTU, DL, TTI, Options, LlvmHoistCommonSkipLimit);
		bool _changed = false;
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
			_changed |= opt.run(&BB);
			while (BBIt != F.end() && DTU.isBBPendingDeletion(&*BBIt))
				++BBIt;
			DTU.flush(); // (required because otherwise blocks are removed before update is applied)
			if (DTU.isBBPendingDeletion(&BB))
				continue;
			_changed |= SimplifyCFG2Pass_normalizeLookupTableIndex(BB);
			_changed |= SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData(DTU,
					BB);
		}
		changed |= _changed;
		_changed = false;
		for (Function::iterator BBIt = F.begin(); BBIt != F.end();) {
			//auto _PA = PreservedAnalyses::all();
			////_PA.abandon<DominatorTreeAnalysis>();
			//AM.invalidate(F, _PA);
			//DT = &AM.getResult<DominatorTreeAnalysis>(F);
			//auto _DTU = DomTreeUpdater(DT, DomTreeUpdater::UpdateStrategy::Lazy);

			// continue rewriting this block while it is updated
			if (SimplifyCFG2Pass_aggresiveStoreSink(DTU, *BBIt)) {
				_changed = true;
			} else if (SimplifyCFG2Pass_mergePredecessorsStore(DTU, *BBIt)) {
				_changed = true;
			} else {
				BBIt++;
			}
		}

		DTU.flush();
		changed |= _changed;
		if (!_changed)
			break;

		itCntr++;
		assert(itCntr < 1000 && "SimplifyCFGPass2 did not converge");
	}

	if (changed) {
		PreservedAnalyses PA;
		if (RequireAndPreserveDomTree)
			PA.preserve<DominatorTreeAnalysis>();
		return PA;
	}
	return FirstPA;
}

}
