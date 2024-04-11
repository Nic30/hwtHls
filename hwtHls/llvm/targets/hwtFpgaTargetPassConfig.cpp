#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>

#include <llvm/Analysis/CFGPrinter.h>
#include <llvm/CodeGen/GlobalISel/IRTranslator.h>
#include <llvm/CodeGen/GlobalISel/InstructionSelect.h>
#include <llvm/CodeGen/GlobalISel/RegBankSelect.h>
#include <llvm/CodeGen/GlobalISel/Legalizer.h>
#include <llvm/CodeGen/GlobalISel/LoadStoreOpt.h>

#include <llvm/CodeGen/StackProtector.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Scalar/GVN.h>

#include <hwtHls/llvm/targets/Analysis/registerBitWidth.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreLegalizerCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreRegAllocCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreToNetlistCombiner.h>
#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>
#include <hwtHls/llvm/targets/Transforms/completeLiveVRegs.h>
#include <hwtHls/llvm/targets/Transforms/EarlyMachineCopyPropagation.h>
#include <hwtHls/llvm/targets/Transforms/hwtHlsCodeGenPrepare.h>
#include <hwtHls/llvm/targets/Transforms/machineDumpAndExitPass.h>
#include <hwtHls/llvm/targets/Transforms/vregIfConversion.h>
#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>

#include <iostream>

namespace llvm {

// :note: you can use 	addPass(new hwtHls::MachineDumpAndExitPass(true, false)); to peek into compilation programatically

void HwtFpgaTargetPassConfig::addStraightLineScalarOptimizationPasses() {
	// from AMDGPU
	addPass(createLICMPass());
	addPass(createSeparateConstOffsetFromGEPPass());
	addPass(createSpeculativeExecutionPass());
	// ReassociateGEPs exposes more opportunities for SLSR. See
	// the example in reassociate-geps-and-slsr.ll.
	addPass(createStraightLineStrengthReducePass());
	// SeparateConstOffsetFromGEP and SLSR creates common expressions which GVN or
	// EarlyCSE can reuse.
	addPass(createGVNPass());
	// Run NaryReassociate after EarlyCSE/GVN to be more effective.
	addPass(createNaryReassociatePass());
	// NaryReassociate on GEPs creates redundant common expressions, so run
	// EarlyCSE after it.
	addPass(createEarlyCSEPass());
}

void HwtFpgaTargetPassConfig::addIRPasses() {
	// based on AMDGPU
	const auto &TM = getHwtFpgaTargetMachine();
	if (TM.getOptLevel() > CodeGenOpt::None) {
		addPass(createSROAPass());
		addStraightLineScalarOptimizationPasses();
	}
	TargetPassConfig::addIRPasses();
	addPass(createGVNPass());
	// based on AArch64
	addPass(createSelectOptimizePass());
}

void HwtFpgaTargetPassConfig::addCodeGenPrepare() {
	if (getOptLevel() != llvm::CodeGenOpt::None)
		addPass(new hwtHls::HwtHlsCodeGenPrepare());
}

bool HwtFpgaTargetPassConfig::addInstSelector() {
	// No instruction selector to install.
	llvm_unreachable(
			"Only GlobalISel should be used using addGlobalInstructionSelect");
	return true;
}
bool HwtFpgaTargetPassConfig::addPreISel() {
	// Add both the safe stack and the stack protection passes: each of them will
	// only protect functions that have corresponding attributes.
	//addPass(new SafeStackPass());
	addPass(new StackProtector());
	if (TM->getOptLevel() > CodeGenOpt::None) {
		addPass(createFlattenCFGPass()); // from AMDGPU
	}
	return false;
}

bool HwtFpgaTargetPassConfig::addIRTranslator() {
	//addPass(new hwtHls::MachineDumpAndExitPass(true, true));
	//addPass(llvm::createCFGPrinterLegacyPassPass());
	addPass(new IRTranslator(getOptLevel()));
	//addPass(new hwtHls::MachineDumpAndExitPass(true, true));
	return false;
}

void HwtFpgaTargetPassConfig::addPreLegalizeMachineIR() {
	// concat, slice calls to instructions
	addPass(createHwtFpgaPreLegalizerCombiner());
	// based on AArch64
	addPass(new LoadStoreOpt());
}

bool HwtFpgaTargetPassConfig::addLegalizeMachineIR() {
	addVerifyPass("before legalize");
	addPass(new Legalizer());
	addVerifyPass("after legalize");
	return false;
}

bool HwtFpgaTargetPassConfig::addRegBankSelect() {
	addPass(new RegBankSelect());
	return false;
}

bool HwtFpgaTargetPassConfig::addGlobalInstructionSelect() {
	addPass(new InstructionSelect(getOptLevel()));
	return false;
}

bool HwtFpgaTargetPassConfig::addILPOpts() {
	// selection of X86PassConfig::addILPOpts()
	addPass(&EarlyIfPredicatorID);
	addPass(&EarlyIfConverterID);
	return false;
}

void HwtFpgaTargetPassConfig::addOptimizedRegAlloc() {
	// :note: nearly same as TargetPassConfig::addOptimizedRegAlloc()
	//   but we do not call scheduler
	// addPass(hwtHls::createCheapBlockInlinePass());
	addPass(&DetectDeadLanesID);
	addPass(&ProcessImplicitDefsID);

	// LiveVariables currently requires pure SSA form.
	//
	// FIXME: Once TwoAddressInstruction pass no longer uses kill flags,
	// LiveVariables can be removed completely, and LiveIntervals can be directly
	// computed. (We still either need to regenerate kill flags after regalloc, or
	// preferably fix the scavenger to not depend on them).
	// FIXME: UnreachableMachineBlockElim is a dependant pass of LiveVariables.
	// When LiveVariables is removed this has to be removed/moved either.
	// Explicit addition of UnreachableMachineBlockElim allows stopping before or
	// after it with -stop-before/-stop-after.
	addPass(&UnreachableMachineBlockElimID);
	addPass(&LiveVariablesID);

	// Edge splitting is smarter with machine loop info.
	addPass(&MachineLoopInfoID);
	addPass(&OptimizePHIsID);
	addPass(&PeepholeOptimizerID);
	//addPass(&MIRCanonicalizerID); // from some reason generates corrupted PHIs with non-existing blocks
	addPass(&PHIEliminationID); // now it becomes NonSSA

	// Eventually, we want to run LiveIntervals before PHI elimination.
	//if (EarlyLiveIntervals)
	addPass(&LiveIntervalsID); // add killed and other attributes

	//addPass(&TwoAddressInstructionPassID, false);
	//addPass(&RegisterCoalescerID);

	// The machine scheduler may accidentally create disconnected components
	// when moving subregister definitions around, avoid this by splitting them to
	// separate vregs before. Splitting can also improve reg. allocation quality.
	//addPass(&RenameIndependentSubregsID); // no subregs there

	// PreRA instruction scheduling.
	//addPass(&MachineSchedulerID);

	//if (addRegAssignAndRewriteOptimized()) {
	// Perform stack slot coloring and post-ra machine LICM.
	//
	// FIXME: Re-enable coloring with register when it's capable of adding
	// kill markers.
	//addPass(&StackSlotColoringID);

	// Allow targets to expand pseudo instructions depending on the choice of
	// registers before MachineCopyPropagation.
	addPostRewrite();

	// Copy propagate to forward register uses and try to eliminate COPYs that
	// were not coalesced.
	addPass(&hwtHls::EarlyMachineCopyPropagationID);

	// Run post-ra machine LICM to hoist reloads / remats.
	//addPass(&EarlyMachineLICMID);
	//}
	addPass(&BranchFolderPassID);
	addPass(&MachineCombinerID);
	addPass(&DeadMachineInstructionElimID); // requires explicit undefs
	//addPass(createMachineVerifierPass("After HwtFpgaTargetPassConfig::addOptimizedRegAlloc"));

	//addPass(createIfConverter([](const MachineFunction &MF) {
	//  return true;
	//}));
	//addPass(&MachineCSEID); // requires IsSSA
	addPass(&LiveIntervalsID); // add killed and other attributes

	addPass(createHwtFpgaPreRegAllocCombiner());
	_addBlockReductionPasses();
}

void HwtFpgaTargetPassConfig::_addBlockReductionPasses() {
	addPass(hwtHls::createCheapBlockInlinePass());
	addPass(&LiveIntervalsID); // add killed and other attributes
	addPass(hwtHls::createCompleteLiveVRegsPass());
	addPass(&hwtHls::EarlyMachineCopyPropagationID);
	addPass(&DeadMachineInstructionElimID); // requires explicit undefs
	addPass(&BranchFolderPassID);
	addPass(&MachineCombinerID);
}

void HwtFpgaTargetPassConfig::addMachinePasses() {
	// based on TargetPassConfig::addMachinePasses();

	// Add passes that optimize machine instructions in SSA form.
	addMachineSSAOptimization();

	if (TM->Options.EnableIPRA)
		addPass(createRegUsageInfoPropPass());

	// Run pre-ra passes.
	addPreRegAlloc();
	addOptimizedRegAlloc();

	addPass(&RemoveRedundantDebugValuesID);
	addPass(&FixupStatepointCallerSavedID);

	// Run pre-sched2 passes.
	addPreSched2();

	// Insert before XRay Instrumentation.
	addPass(&FEntryInserterID);

	addPass(createHwtFpgaPreToNetlistCombiner());
	// because InstructionSelect::runOnMachineFunction() intentionally removes all types using MRI.clearVirtRegTypes();
	// we need to regenerate this information
	addPass(new hwtHls::HwtFpgaRegisterBitWidth());
	addPass(&MachineLoopInfoID);
	addPass(&LiveIntervalsID); // add killed and other attributes

	addPass(new hwtHls::HwtFpgaToNetlist());
}

// [todo] handling of register allocation, maybe similar to WebAssemblyPassConfig::addPostRegAlloc()
void HwtFpgaTargetPassConfig::addPreSched2() {
	addPass(hwtHls::createVRegIfConverter(nullptr));
}

AnalysisID HwtFpgaTargetPassConfig::_testAddPass(AnalysisID PassID) {
	return addPass(PassID);
}

void HwtFpgaTargetPassConfig::_testAddPass(Pass *P) {
	addPass(P);
}

FunctionPass* HwtFpgaTargetPassConfig::createTargetRegisterAllocator(
		bool Optimized) {
	llvm_unreachable(
			"createTargetRegisterAllocator should not be called because there is no RegisterAllocator");
	//return createFastRegisterAllocator();
	return nullptr; // No reg alloc, same as WebAssembly
}

}
