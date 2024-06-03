//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the legalizer.
//
//===----------------------------------------------------------------------===//
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreLegalizerCombiner.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

#include <llvm/CodeGen/GlobalISel/CSEInfo.h>
#include <llvm/CodeGen/GlobalISel/Combiner.h>
#include <llvm/CodeGen/GlobalISel/CombinerInfo.h>
#include <llvm/CodeGen/GlobalISel/GIMatchTableExecutorImpl.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#define GET_GICOMBINER_DEPS
#include "HwtFpgaGenPreLegalizerGICombiner.inc"
#undef GET_GICOMBINER_DEPS

#define DEBUG_TYPE "hwtfpga-prelegalizer-combiner"

using namespace llvm;

namespace {

#define GET_GICOMBINER_TYPES
#include "HwtFpgaGenPreLegalizerGICombiner.inc"
#undef GET_GICOMBINER_TYPES

class HwtFpgaPreLegalizerGICombinerImpl: public Combiner {
protected:
	mutable HwtFpgaCombinerHelper Helper;
	const HwtFpgaPreLegalizerGICombinerImplRuleConfig &RuleConfig;
	const HwtFpgaTargetSubtarget &STI;
public:
	HwtFpgaPreLegalizerGICombinerImpl(
			MachineFunction &MF, CombinerInfo &CInfo, const TargetPassConfig *TPC,
	      GISelKnownBits &KB, GISelCSEInfo *CSEInfo,
	      const HwtFpgaPreLegalizerGICombinerImplRuleConfig &RuleConfig,
	      const HwtFpgaTargetSubtarget &STI, MachineDominatorTree *MDT,
	      const LegalizerInfo *LI);
	  static const char *getName() { return "HwtFpgaPreLegalizerGICombiner"; }
	  bool tryCombineAll(MachineInstr &I) const override;
private:
#define GET_GICOMBINER_CLASS_MEMBERS
#include "HwtFpgaGenPreLegalizerGICombiner.inc"
#undef GET_GICOMBINER_CLASS_MEMBERS
};

#define GET_GICOMBINER_IMPL
#include "HwtFpgaGenPreLegalizerGICombiner.inc"
#undef GET_GICOMBINER_IMPL


HwtFpgaPreLegalizerGICombinerImpl::HwtFpgaPreLegalizerGICombinerImpl(
    MachineFunction &MF, CombinerInfo &CInfo, const TargetPassConfig *TPC,
    GISelKnownBits &KB, GISelCSEInfo *CSEInfo,
    const HwtFpgaPreLegalizerGICombinerImplRuleConfig &RuleConfig,
    const HwtFpgaTargetSubtarget &STI, MachineDominatorTree *MDT,
    const LegalizerInfo *LI)
    : Combiner(MF, CInfo, TPC, &KB, CSEInfo),
      Helper(Observer, B, /*IsPreLegalize*/ false, &KB, MDT, LI),
      RuleConfig(RuleConfig), STI(STI),
#define GET_GICOMBINER_CONSTRUCTOR_INITS
#include "HwtFpgaGenPreLegalizerGICombiner.inc"
#undef GET_GICOMBINER_CONSTRUCTOR_INITS
{
}

// Pass boilerplate
// ================

class HwtFpgaPreLegalizerCombiner: public MachineFunctionPass {
public:
	static char ID;

	HwtFpgaPreLegalizerCombiner();

	StringRef getPassName() const override {
		return "HwtFpgaPreLegalizerCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;
	void getAnalysisUsage(AnalysisUsage &AU) const override;
private:
	HwtFpgaPreLegalizerGICombinerImplRuleConfig RuleConfig;
};
} // end anonymous namespace

void HwtFpgaPreLegalizerCombiner::getAnalysisUsage(
		AnalysisUsage &AU) const {
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

HwtFpgaPreLegalizerCombiner::HwtFpgaPreLegalizerCombiner() :
		MachineFunctionPass(ID) {
	initializeHwtFpgaPreLegalizerCombinerPass(
			*PassRegistry::getPassRegistry());
	if (!RuleConfig.parseCommandLineOption())
	  report_fatal_error("Invalid rule identifier");
}

bool HwtFpgaPreLegalizerCombiner::runOnMachineFunction(
		MachineFunction &MF) {
	if (MF.getProperties().hasProperty(
	        MachineFunctionProperties::Property::FailedISel))
	  return false;
	assert(!MF.getProperties().hasProperty(
	           MachineFunctionProperties::Property::Legalized) &&
	       "Expected a non-legalized function?");
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
	HwtFpgaPreLegalizerGICombinerImpl Impl(MF, CInfo, TPC, *KB, CSEInfo,
	                                      RuleConfig, ST, MDT, LI);
	return Impl.combineMachineInstrs();
}

char HwtFpgaPreLegalizerCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(HwtFpgaPreLegalizerCombiner, DEBUG_TYPE,
		"Combine HwtFpga machine instrs before legalization",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(HwtFpgaPreLegalizerCombiner, DEBUG_TYPE,
			"Combine HwtFpga machine instrs before legalization", false,
			false)

namespace llvm {

FunctionPass* createHwtFpgaPreLegalizerCombiner() {
	return new HwtFpgaPreLegalizerCombiner();
}
} // end namespace llvm
