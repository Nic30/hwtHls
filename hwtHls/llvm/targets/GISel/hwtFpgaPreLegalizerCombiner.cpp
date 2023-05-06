//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the legalizer.
//
//===----------------------------------------------------------------------===//
#include "hwtFpgaPreLegalizerCombiner.h"
#include "../hwtFpgaTargetMachine.h"

#include <llvm/CodeGen/GlobalISel/Combiner.h>
#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <llvm/CodeGen/GlobalISel/CombinerInfo.h>
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
#include "hwtFpgaCombinerHelper.h"

#define DEBUG_TYPE "genericfpga-prelegalizer-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class HwtFpgaGenPreLegalizeGICombinerHelperState {
protected:
	HwtFpgaCombinerHelper &Helper;

public:
	HwtFpgaGenPreLegalizeGICombinerHelperState(HwtFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "HwtFpgaGenPreLegalizeGICombiner.inc"
#undef HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "HwtFpgaGenPreLegalizeGICombiner.inc"
#undef HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_H

class HwtFpgaPreLegalizerCombinerInfo: public CombinerInfo {
	bool IsPreLegalize;
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	HwtFpgaGenPreLegalizeGICombinerHelperRuleConfig GeneratedRuleCfg;

public:
	HwtFpgaPreLegalizerCombinerInfo(bool EnableOpt, bool OptSize,
			bool MinSize, bool IsPreLegalize, GISelKnownBits *KB,
			MachineDominatorTree *MDT, const LegalizerInfo *LI) :
			CombinerInfo(/*AllowIllegalOps*/true, /*ShouldLegalizeIllegal*/
			false, LI, EnableOpt, OptSize, MinSize), IsPreLegalize(
					IsPreLegalize), KB(KB), MDT(MDT) {
		if (!GeneratedRuleCfg.parseCommandLineOption())
			report_fatal_error("Invalid rule identifier");
	}

	virtual bool combine(GISelChangeObserver &Observer, MachineInstr &MI,
			MachineIRBuilder &B) const override;
};

bool HwtFpgaPreLegalizerCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	HwtFpgaCombinerHelper Helper(Observer, B, IsPreLegalize, KB, MDT, LInfo);
	HwtFpgaGenPreLegalizeGICombinerHelper Generated(GeneratedRuleCfg,
			Helper);

	if (Generated.tryCombineAll(Observer, MI, B))
		return true;

	unsigned Opc = MI.getOpcode();
	switch (Opc) {
	case TargetOpcode::G_CONCAT_VECTORS:
		return Helper.tryCombineConcatVectors(MI);
	case TargetOpcode::G_SHUFFLE_VECTOR:
		return Helper.tryCombineShuffleVector(MI);
	case TargetOpcode::G_MEMCPY_INLINE:
		return Helper.tryEmitMemcpyInline(MI);
	case TargetOpcode::G_MEMCPY:
	case TargetOpcode::G_MEMMOVE:
	case TargetOpcode::G_MEMSET: {
		// If we're at -O0 set a maxlen of 32 to inline, otherwise let the other
		// heuristics decide.
		unsigned MaxLen = EnableOpt ? 0 : 32;
		// Try to inline memcpy type calls if optimizations are enabled.
		if (Helper.tryCombineMemCpyFamily(MI, MaxLen))
			return true;
		return false;
	}
	}

	return false;
}

#define HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "HwtFpgaGenPreLegalizeGICombiner.inc"
#undef HWTFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_CPP

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
}

bool HwtFpgaPreLegalizerCombiner::runOnMachineFunction(
		MachineFunction &MF) {
	if (MF.getProperties().hasProperty(
			MachineFunctionProperties::Property::FailedISel))
		return false;
	auto &TPC = getAnalysis<TargetPassConfig>();

	// Enable CSE.
	GISelCSEAnalysisWrapper &Wrapper =
			getAnalysis<GISelCSEAnalysisWrapperPass>().getCSEWrapper();
	auto *CSEInfo = &Wrapper.get(TPC.getCSEConfig());

	const Function &F = MF.getFunction();
	bool EnableOpt = MF.getTarget().getOptLevel() != CodeGenOpt::None
			&& !skipFunction(F);
	GISelKnownBits *KB = &getAnalysis<GISelKnownBitsAnalysis>().get(MF);
	MachineDominatorTree *MDT = &getAnalysis<MachineDominatorTree>();
	const LegalizerInfo *LInfo = ((const HwtFpgaTargetSubtarget *)&MF.getSubtarget())->getLegalizerInfo();
	HwtFpgaPreLegalizerCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), true, KB, MDT, LInfo);
	Combiner C(PCInfo, &TPC);
	return C.combineMachineInstrs(MF, CSEInfo);
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
