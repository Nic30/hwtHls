//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the register allocation.
//
//===----------------------------------------------------------------------===//
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreRegAllocCombiner.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

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

#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#define DEBUG_TYPE "hwtfpga-preregalloc-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class HwtFpgaGenPreRegAllocGICombinerHelperState {
protected:
	HwtFpgaCombinerHelper &Helper;

public:
	HwtFpgaGenPreRegAllocGICombinerHelperState(HwtFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_H

class HwtFpgaPreRegAllocCombinerInfo: public CombinerInfo {
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	HwtFpgaGenPreRegAllocGICombinerHelperRuleConfig GeneratedRuleCfg;

public:
	HwtFpgaPreRegAllocCombinerInfo(bool EnableOpt, bool OptSize,
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

bool HwtFpgaPreRegAllocCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	HwtFpgaCombinerHelper Helper(Observer, B, false, KB, MDT, LInfo);
	HwtFpgaGenPreRegAllocGICombinerHelper Generated(GeneratedRuleCfg,
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

#define HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "HwtFpgaGenPreRegAllocGICombiner.inc"
#undef HWTFPGAGENPREREGALLOCGICOMBINERHELPER_GENCOMBINERHELPER_CPP

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
}

bool HwtFpgaPreRegAllocCombiner::runOnMachineFunction(MachineFunction &MF) {
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
	HwtFpgaPreRegAllocCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), KB, MDT);
	Combiner C(PCInfo, &TPC);
	return C.combineMachineInstrs(MF, CSEInfo);
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
