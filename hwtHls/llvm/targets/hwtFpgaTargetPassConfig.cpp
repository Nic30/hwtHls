#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>

#include <llvm/Analysis/CFGPrinter.h>
#include <llvm/CodeGen/GlobalISel/InstructionSelect.h>
#include <llvm/CodeGen/GlobalISel/RegBankSelect.h>
#include <llvm/CodeGen/GlobalISel/Legalizer.h>
#include <llvm/CodeGen/GlobalISel/LoadStoreOpt.h>

#include <llvm/CodeGen/StackProtector.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Scalar/GVN.h>
#include <llvm/CodeGen/GlobalISel/CSEInfo.h>

#include <hwtHls/llvm/targets/Analysis/registerBitWidth.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaIRTranslator.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreLegalizerCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreRegAllocCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreToNetlistCombiner.h>
#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>
#include <hwtHls/llvm/targets/Transforms/completeLiveVRegs.h>
#include <hwtHls/llvm/targets/Transforms/EarlyMachineCopyPropagation.h>
#include <hwtHls/llvm/targets/Transforms/hwtHlsCodeGenPrepare.h>
#include <hwtHls/llvm/targets/Transforms/machineDumpAndExitPass.h>
#include <hwtHls/llvm/targets/Transforms/RemovePointerArithmeticPass.h>
#include <hwtHls/llvm/targets/Transforms/vregIfConversion.h>
#include <hwtHls/llvm/targets/Transforms/vregMachineLateInstrsCleanup.h>
#include <hwtHls/llvm/targets/Transforms/HwtHlsRunPassInstrumentationCallbacksPass.h>
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
	if (TM.getOptLevel() > CodeGenOptLevel::None) {
		addPass(createSROAPass());
		addStraightLineScalarOptimizationPasses();
	}
	TargetPassConfig::addIRPasses();
	addPass(createGVNPass());
	// based on AArch64
	addPass(createSelectOptimizePass());
}

void HwtFpgaTargetPassConfig::addCodeGenPrepare() {
	if (getOptLevel() != CodeGenOptLevel::None)
		addPass(new hwtHls::HwtHlsCodeGenPrepareLegacyPass());
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
	if (TM->getOptLevel() > CodeGenOptLevel::None) {
		addPass(createFlattenCFGPass()); // from AMDGPU
	}
	return false;
}

bool HwtFpgaTargetPassConfig::addIRTranslator() {
	//addPass(new hwtHls::MachineDumpAndExitPass(true, true));
	//addPass(llvm::createCFGPrinterLegacyPassPass());
	addPass(new hwtHls::HwtFpgaIRTranslator(getOptLevel()));
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
	// addPass(new hwtHls::MachineDumpAndExitPass(true, false));
	addPass(new InstructionSelect(getOptLevel()));
	addPass(hwtHls::createRemovePointerArithmeticPass());
	// addPass(new hwtHls::MachineDumpAndExitPass(true, true));
	return false;
}

bool HwtFpgaTargetPassConfig::addILPOpts() {
	// selection of X86PassConfig::addILPOpts()
	addPass(&MachineCSEID); // hwtHls specific
	addPass(&EarlyIfPredicatorID);
	addPass(&EarlyIfConverterID);
	addPass(&MachineCSEID); // hwtHls specific
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
	addPass(hwtHls::createVRegMachineLateInstrsCleanup());
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
	addPass(hwtHls::createVRegMachineLateInstrsCleanup());
	addPass(hwtHls::createVRegIfConverter(nullptr));
	addPass(hwtHls::createVRegMachineLateInstrsCleanup());
}

class HwtFpgaCSEConfig: public CSEConfigFull {
public:
	virtual bool shouldCSEOpc(unsigned Opc) override {
		if (CSEConfigFull::shouldCSEOpc(Opc))
			return true;
		switch (Opc) {
		case HwtFpga::HWTFPGA_EXTRACT:
		case HwtFpga::HWTFPGA_MERGE_VALUES:
		case HwtFpga::HWTFPGA_NOT:
		case HwtFpga::HWTFPGA_MUX:
		case HwtFpga::HWTFPGA_ADD:
		case HwtFpga::HWTFPGA_AND:
		case HwtFpga::HWTFPGA_ICMP:
		case HwtFpga::HWTFPGA_MUL:
		case HwtFpga::HWTFPGA_UDIV:
		case HwtFpga::HWTFPGA_SDIV:
		case HwtFpga::HWTFPGA_UREM:
		case HwtFpga::HWTFPGA_SREM:
		case HwtFpga::HWTFPGA_OR:
		case HwtFpga::HWTFPGA_SUB:
		case HwtFpga::HWTFPGA_XOR:
		case HwtFpga::HWTFPGA_CTLZ_ZERO_UNDEF:
		case HwtFpga::HWTFPGA_CTTZ_ZERO_UNDEF:
		case HwtFpga::HWTFPGA_CTLZ:
		case HwtFpga::HWTFPGA_CTTZ:
		case HwtFpga::HWTFPGA_CTPOP:
			return true;
		default:
			return false;
		};
	}
};

std::unique_ptr<CSEConfigBase> HwtFpgaTargetPassConfig::getCSEConfig() const {
	return std::make_unique<HwtFpgaCSEConfig>();
}
void HwtFpgaTargetPassConfig::setPassInstrumentationCallbacks(
		llvm::PassInstrumentationCallbacks *PIC) {
	PI = PassInstrumentation(PIC);
}

void HwtFpgaTargetPassConfig::addPassCallbackFromPI(Pass *P) {
	std::string passName = "<unknown pass>";
	if (P) {
		passName = P->getPassName();
	}
	if (dynamic_cast<llvm::MachineFunctionPass*>(P)) {
		llvm::TargetPassConfig::addPass(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass(
						PI, passName));
	} else if (dynamic_cast<llvm::FunctionPass*>(P)) {
		llvm::TargetPassConfig::addPass(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksFunctionPass(
						PI, passName));
	} else if (dynamic_cast<llvm::LoopPass*>(P)) {
		llvm::TargetPassConfig::addPass(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksLoopPass(PI,
						passName));
	} else {
		errs() << passName << "\n";
		llvm_unreachable("Unknown type of pass");
	}

}
AnalysisID HwtFpgaTargetPassConfig::addPass(AnalysisID PassID) {
	auto FinalID = llvm::TargetPassConfig::addPass(PassID);
	IdentifyingPassPtr TargetID = getPassSubstitution(FinalID);
	if (!TargetID.isValid())
		return nullptr;

	Pass *P;
	if (TargetID.isInstance())
		P = TargetID.getInstance();
	else {
		P = Pass::createPass(TargetID.getID());
	}
	addPassCallbackFromPI(P);
	return FinalID;
}
void HwtFpgaTargetPassConfig::addPass(Pass *P) {
	llvm::TargetPassConfig::addPass(P);
	addPassCallbackFromPI(P);
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
