//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the register allocation.
//
//===----------------------------------------------------------------------===//
#include "genericFpgaPreRegAllocCombiner.h"
#include "../genericFpgaTargetMachine.h"

#include <llvm/CodeGen/GlobalISel/Combiner.h>
#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <llvm/CodeGen/GlobalISel/CombinerInfo.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>

#include "genericFpgaCombinerHelper.h"

#define DEBUG_TYPE "genericfpga-preregalloc-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class GenericFpgaGenPreRegAllocGICombinerHelperState {
protected:
	GenFpgaCombinerHelper &Helper;

public:
	GenericFpgaGenPreRegAllocGICombinerHelperState(GenFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "GenericFpgaGenPreRegAllocGICombiner.inc"
#undef GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "GenericFpgaGenPreRegAllocGICombiner.inc"
#undef GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_H

class GenericFpgaPreRegAllocCombinerInfo: public CombinerInfo {
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	GenericFpgaGenPreRegAllocGICombinerHelperRuleConfig GeneratedRuleCfg;

public:
	GenericFpgaPreRegAllocCombinerInfo(bool EnableOpt, bool OptSize,
			bool MinSize, GISelKnownBits *KB, MachineDominatorTree *MDT) :
			CombinerInfo(/*AllowIllegalOps*/true, /*ShouldRegAllocIllegal*/
			false,
			/*RegAllocInfo*/nullptr, EnableOpt, OptSize, MinSize), KB(KB), MDT(
					MDT) {
		if (!GeneratedRuleCfg.parseCommandLineOption())
			report_fatal_error("Invalid rule identifier");
	}

	virtual bool combine(GISelChangeObserver &Observer, MachineInstr &MI,
			MachineIRBuilder &B) const override;
};

bool GenericFpgaPreRegAllocCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	GenFpgaCombinerHelper Helper(Observer, B, KB, MDT);
	GenericFpgaGenPreRegAllocGICombinerHelper Generated(GeneratedRuleCfg,
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
	}

	return false;
}

#define GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "GenericFpgaGenPreRegAllocGICombiner.inc"
#undef GENERICFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_CPP

// Pass boilerplate
// ================

class GenericFpgaPreRegAllocCombiner: public MachineFunctionPass {
public:
	static char ID;

	GenericFpgaPreRegAllocCombiner();

	StringRef getPassName() const override {
		return "GenericFpgaPreRegAllocCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	void getAnalysisUsage(AnalysisUsage &AU) const override;
};
} // end anonymous namespace

void GenericFpgaPreRegAllocCombiner::getAnalysisUsage(AnalysisUsage &AU) const {
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

GenericFpgaPreRegAllocCombiner::GenericFpgaPreRegAllocCombiner() :
		MachineFunctionPass(ID) {
	initializeGenericFpgaPreRegAllocCombinerPass(
			*PassRegistry::getPassRegistry());
}

bool GenericFpgaPreRegAllocCombiner::runOnMachineFunction(MachineFunction &MF) {
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
	GenericFpgaPreRegAllocCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), KB, MDT);
	Combiner C(PCInfo, &TPC);
	return C.combineMachineInstrs(MF, CSEInfo);
}

char GenericFpgaPreRegAllocCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(GenericFpgaPreRegAllocCombiner, DEBUG_TYPE,
		"Combine GenericFpga machine instrs before register allocation",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(GenericFpgaPreRegAllocCombiner, DEBUG_TYPE,
			"Combine GenericFpga machine instrs before register allocation",
			false, false)

namespace llvm {

FunctionPass* createGenericFpgaPreRegAllocCombiner() {
	return new GenericFpgaPreRegAllocCombiner();
}

} // end namespace llvm
