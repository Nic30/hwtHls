//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the register allocation.
//
// :note: code structure based on hwtFpgaPreToNetlistCombiner.cpp
//===----------------------------------------------------------------------===//
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreRegAllocCombiner.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

#include <llvm/CodeGen/GlobalISel/Combiner.h>
#include <llvm/CodeGen/GlobalISel/CombinerInfo.h>
#include <llvm/CodeGen/GlobalISel/GIMatchTableExecutorImpl.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/CSEInfo.h>
#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>

#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#define DEBUG_TYPE "hwtfpga-preregalloc-combiner"

using namespace llvm;
using namespace MIPatternMatch;

#define GET_GICOMBINER_DEPS
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef GET_GICOMBINER_DEPS

namespace {

#define GET_GICOMBINER_TYPES
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef GET_GICOMBINER_TYPES

class HwtFpgaPreRegAllocGICombinerImpl: public Combiner {
protected:
	mutable HwtFpgaCombinerHelper Helper;
	const HwtFpgaPreRegAllocGICombinerImplRuleConfig &RuleConfig;
	const HwtFpgaTargetSubtarget &STI;
public:
	HwtFpgaPreRegAllocGICombinerImpl(
      MachineFunction &MF, CombinerInfo &CInfo, const TargetPassConfig *TPC,
      GISelKnownBits &KB, GISelCSEInfo *CSEInfo,
      const HwtFpgaPreRegAllocGICombinerImplRuleConfig &RuleConfig,
      const HwtFpgaTargetSubtarget &STI, MachineDominatorTree *MDT,
      const LegalizerInfo *LI);

  static const char *getName() { return "HwtFpgaPreRegAllocCombiner"; }

  bool tryCombineAll(MachineInstr &I) const override;

private:
#define GET_GICOMBINER_CLASS_MEMBERS
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef GET_GICOMBINER_CLASS_MEMBERS
};
#define GET_GICOMBINER_IMPL
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef GET_GICOMBINER_IMPL

HwtFpgaPreRegAllocGICombinerImpl::HwtFpgaPreRegAllocGICombinerImpl(
    MachineFunction &MF, CombinerInfo &CInfo, const TargetPassConfig *TPC,
    GISelKnownBits &KB, GISelCSEInfo *CSEInfo,
    const HwtFpgaPreRegAllocGICombinerImplRuleConfig &RuleConfig,
    const HwtFpgaTargetSubtarget &STI, MachineDominatorTree *MDT,
    const LegalizerInfo *LI)
    : Combiner(MF, CInfo, TPC, &KB, CSEInfo),
      Helper(Observer, B, /*IsPreLegalize*/ false, &KB, MDT, LI),
      RuleConfig(RuleConfig), STI(STI),
#define GET_GICOMBINER_CONSTRUCTOR_INITS
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef GET_GICOMBINER_CONSTRUCTOR_INITS
{
}


// Pass boilerplate
// ================

class HwtFpgaPreRegAllocCombiner: public MachineFunctionPass {
public:
	static char ID;

	HwtFpgaPreRegAllocCombiner();

	StringRef getPassName() const override {
		return "HwtFpgaPreRegAllocCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;
	void getAnalysisUsage(AnalysisUsage &AU) const override;
private:
	HwtFpgaPreRegAllocGICombinerImplRuleConfig RuleConfig;
};
} // end anonymous namespace

void HwtFpgaPreRegAllocCombiner::getAnalysisUsage(AnalysisUsage &AU) const {
	AU.addRequired<TargetPassConfig>();
	AU.setPreservesCFG();
	getSelectionDAGFallbackAnalysisUsage(AU);
	AU.addRequired<GISelKnownBitsAnalysis>();
	AU.addPreserved<GISelKnownBitsAnalysis>();
	AU.addRequired<MachineDominatorTree>();
	AU.addPreserved<MachineDominatorTree>();
	AU.addRequired<GISelCSEAnalysisWrapperPass>();
	AU.addPreserved<GISelCSEAnalysisWrapperPass>();
	MachineFunctionPass::getAnalysisUsage(AU);
}

HwtFpgaPreRegAllocCombiner::HwtFpgaPreRegAllocCombiner() :
		MachineFunctionPass(ID) {
	initializeHwtFpgaPreRegAllocCombinerPass(
			*PassRegistry::getPassRegistry());
	if (!RuleConfig.parseCommandLineOption())
	  report_fatal_error("Invalid rule identifier");
}

bool HwtFpgaPreRegAllocCombiner::runOnMachineFunction(
		MachineFunction &MF) {
	if (MF.getProperties().hasProperty(
	        MachineFunctionProperties::Property::FailedISel))
	  return false;
	assert(MF.getProperties().hasProperty(
	           MachineFunctionProperties::Property::Legalized) &&
	       "Expected a legalized function?");
	auto *TPC = &getAnalysis<TargetPassConfig>();
	const Function &F = MF.getFunction();
	bool EnableOpt =
	    MF.getTarget().getOptLevel() != CodeGenOptLevel::None && !skipFunction(F);

	const HwtFpgaTargetSubtarget &ST = MF.getSubtarget<HwtFpgaTargetSubtarget>();
	const auto *LI = ST.getLegalizerInfo();

	GISelKnownBits *KB = &getAnalysis<GISelKnownBitsAnalysis>().get(MF);
	MachineDominatorTree *MDT = &getAnalysis<MachineDominatorTree>();
	GISelCSEAnalysisWrapper &Wrapper =
	    getAnalysis<GISelCSEAnalysisWrapperPass>().getCSEWrapper();
	auto *CSEInfo = &Wrapper.get(TPC->getCSEConfig());

	CombinerInfo CInfo(/*AllowIllegalOps*/ true, /*ShouldLegalizeIllegal*/ false,
	                   /*LegalizerInfo*/ nullptr, EnableOpt, F.hasOptSize(),
	                   F.hasMinSize());
	HwtFpgaPreRegAllocGICombinerImpl Impl(MF, CInfo, TPC, *KB, CSEInfo,
	                                      RuleConfig, ST, MDT, LI);
	return Impl.combineMachineInstrs();
}

char HwtFpgaPreRegAllocCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(HwtFpgaPreRegAllocCombiner, DEBUG_TYPE,
		"Combine HwtFpga machine instrs before register allocation",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(HwtFpgaPreRegAllocCombiner, DEBUG_TYPE,
			"Combine HwtFpga machine instrs before register allocation",
			false, false)

namespace llvm {

FunctionPass* createHwtFpgaPreRegAllocCombiner() {
	return new HwtFpgaPreRegAllocCombiner();
}

} // end namespace llvm
