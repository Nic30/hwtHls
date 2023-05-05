//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the legalizer.
//
//===----------------------------------------------------------------------===//
#include "genericFpgaPreLegalizerCombiner.h"
#include "../genericFpgaTargetMachine.h"

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
#include "genericFpgaCombinerHelper.h"

#define DEBUG_TYPE "genericfpga-prelegalizer-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class GenericFpgaGenPreLegalizeGICombinerHelperState {
protected:
	GenFpgaCombinerHelper &Helper;

public:
	GenericFpgaGenPreLegalizeGICombinerHelperState(GenFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "GenericFpgaGenPreLegalizeGICombiner.inc"
#undef GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "GenericFpgaGenPreLegalizeGICombiner.inc"
#undef GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_H

class GenericFpgaPreLegalizerCombinerInfo: public CombinerInfo {
	bool IsPreLegalize;
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	GenericFpgaGenPreLegalizeGICombinerHelperRuleConfig GeneratedRuleCfg;

public:
	GenericFpgaPreLegalizerCombinerInfo(bool EnableOpt, bool OptSize,
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

bool GenericFpgaPreLegalizerCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	GenFpgaCombinerHelper Helper(Observer, B, IsPreLegalize, KB, MDT, LInfo);
	GenericFpgaGenPreLegalizeGICombinerHelper Generated(GeneratedRuleCfg,
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

#define GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "GenericFpgaGenPreLegalizeGICombiner.inc"
#undef GENERICFPGAGENPRELEGALIZEGICOMBINERHELPER_GENCOMBINERHELPER_CPP

// Pass boilerplate
// ================

class GenericFpgaPreLegalizerCombiner: public MachineFunctionPass {
public:
	static char ID;

	GenericFpgaPreLegalizerCombiner();

	StringRef getPassName() const override {
		return "GenericFpgaPreLegalizerCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	void getAnalysisUsage(AnalysisUsage &AU) const override;
};
} // end anonymous namespace

void GenericFpgaPreLegalizerCombiner::getAnalysisUsage(
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

GenericFpgaPreLegalizerCombiner::GenericFpgaPreLegalizerCombiner() :
		MachineFunctionPass(ID) {
	initializeGenericFpgaPreLegalizerCombinerPass(
			*PassRegistry::getPassRegistry());
}

bool GenericFpgaPreLegalizerCombiner::runOnMachineFunction(
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
	const LegalizerInfo *LInfo = ((const GenericFpgaTargetSubtarget *)&MF.getSubtarget())->getLegalizerInfo();
	GenericFpgaPreLegalizerCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), true, KB, MDT, LInfo);
	Combiner C(PCInfo, &TPC);
	return C.combineMachineInstrs(MF, CSEInfo);
}

char GenericFpgaPreLegalizerCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(GenericFpgaPreLegalizerCombiner, DEBUG_TYPE,
		"Combine GenericFpga machine instrs before legalization",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(GenericFpgaPreLegalizerCombiner, DEBUG_TYPE,
			"Combine GenericFpga machine instrs before legalization", false,
			false)

namespace llvm {

FunctionPass* createGenericFpgaPreLegalizerCombiner() {
	return new GenericFpgaPreLegalizerCombiner();
}
} // end namespace llvm
