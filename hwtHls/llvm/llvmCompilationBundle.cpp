#include "llvmCompilationBundle.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include <iostream>

#include <llvm/ADT/APInt.h>
#include <llvm/ADT/APSInt.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Pass.h>

//#include <llvm/Transforms/IPO/PassManagerBuilder.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Instrumentation/ControlHeightReduction.h>
#include <llvm/Transforms/AggressiveInstCombine/AggressiveInstCombine.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Scalar/Reassociate.h>
#include <llvm/Transforms/Scalar/NewGVN.h>
#include <llvm/Transforms/Scalar/DCE.h>
#include <llvm/Transforms/Scalar/SCCP.h>
#include <llvm/Transforms/Scalar/SROA.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/Scalar/GVN.h>
#include <llvm/Transforms/Scalar/SpeculativeExecution.h>
#include <llvm/Transforms/Scalar/JumpThreading.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>
#include <llvm/Transforms/Scalar/CorrelatedValuePropagation.h>
#include <llvm/Transforms/Scalar/LoopInstSimplify.h>
#include <llvm/Transforms/Scalar/LoopSimplifyCFG.h>
#include <llvm/Transforms/Scalar/LICM.h>
#include <llvm/Transforms/Scalar/LoopRotation.h>
#include <llvm/Transforms/Scalar/LoopIdiomRecognize.h>
#include <llvm/Transforms/Scalar/IndVarSimplify.h>
#include <llvm/Transforms/Scalar/LoopDeletion.h>
#include <llvm/Transforms/Scalar/MergedLoadStoreMotion.h>
#include <llvm/Transforms/Scalar/BDCE.h>
#include <llvm/Transforms/Scalar/DFAJumpThreading.h>
#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/Transforms/Scalar/MemCpyOptimizer.h>
#include <llvm/Transforms/Scalar/DeadStoreElimination.h>
#include <llvm/Transforms/Scalar/ConstraintElimination.h>
#include <llvm/Transforms/Scalar/SimpleLoopUnswitch.h>
#include <llvm/Transforms/Utils/AssumeBundleBuilder.h>
#include <llvm/Transforms/Utils.h>

#include <llvm/Target/TargetMachine.h>
//#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/CodeGen.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>


#include "targets/genericFpgaTargetInfo.h"
#include "targets/genericFpgaTargetMachine.h"
#include "targets/genericFpgaTargetPassConfig.h"
#include "Transforms/extractBitConcatAndSliceOpsPass.h"
#include "Transforms/bitwidthReducePass/bitwidthReducePass.h"

#include <llvm/CodeGen/MachinePassManager.h>


namespace hwtHls {

LlvmCompilationBundle::LlvmCompilationBundle(const std::string &moduleName) :
		ctx(), strCtx(), mod(strCtx.addStringRef(moduleName), ctx), builder(
				ctx), main(nullptr), MMIWP(nullptr) {
	std::string TargetTriple = "genericFpga-unknown-linux-gnu";
	Target = &getTheGenericFpgaTarget(); //llvm::TargetRegistry::targets()[0];
	Level = llvm::OptimizationLevel::O3;
	EnableO3NonTrivialUnswitching = true;
	EnableGVNHoist = true;
	EnableGVNSink = true;

	auto CPU = "";
	auto Features = "";
	llvm::TargetOptions opt;
	// useless for this target
	opt.XCOFFTracebackTable = false;
	// only GlobalISel implemented (No FastISel, SelectionDAGISel)
	opt.EnableGlobalISel = true;

	auto RM = llvm::Optional<llvm::Reloc::Model>();
	TM = Target->createTargetMachine(TargetTriple, CPU, Features, opt, RM);
	TM->setOptLevel(llvm::CodeGenOpt::Level::Aggressive);
	PTO = llvm::PipelineTuningOptions();
	PB = llvm::PassBuilder(
	/*TargetMachine *TM = */TM,
	/* PipelineTuningOptions PTO = */PTO,
	/*Optional<PGOOptions> PGOOpt =*/llvm::None,
	/*PassInstrumentationCallbacks *PIC =*/nullptr);
	llvm::LLVMTargetMachine &LLVMTM = static_cast<llvm::LLVMTargetMachine&>(*TM);
	MMIWP = new llvm::MachineModuleInfoWrapperPass(&LLVMTM);

}
//void applyDebugOptions() {
//
//	//llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
//	//Map["print-before-all"]->addOccurrence(0, "", "true");
//	//Map["view-dag-combine1-dags"]->addOccurrence(0, "", "true");
//	//Map["view-legalize-types-dags"]->addOccurrence(0, "", "true");
//	//Map["view-dag-combine-lt-dags"]->addOccurrence(0, "", "true");
//	//Map["view-legalize-dags"]->addOccurrence(0, "", "true");
//	//Map["view-dag-combine2-dags"]->addOccurrence(0, "", "true");
//	//Map["view-isel-dags"]->addOccurrence(0, "", "true");
//	//Map["view-sched-dags"]->addOccurrence(0, "", "true");
//	//Map["view-sunit-dags"]->addOccurrence(0, "", "true");
//	//Map["print-after-isel"]->addOccurrence(0, "", "true");
//	//Map["debug-only"]->addOccurrence(0, "", "mir-canonicalizer");
//	// "early-ifcvt-limit"
//	//Map["print-lsr-output"]->setValueStr("true");
//
//}

void LlvmCompilationBundle::runOpt(hwtHls::GenericFpgaToNetlist::ConvesionFnT toNetlist) {
	assert(
			main
					&& "a main function must be created before call of this function");
	auto &fn = *main;
	// https://stackoverflow.com/questions/51934964/function-optimization-pass
	// @see PassBuilder::buildFunctionSimplificationPipeline

	// [todo] PassBuilder::addVectorPasses

	fn.getParent()->setDataLayout(TM->createDataLayout());

	auto LAM = llvm::LoopAnalysisManager { };
	auto cgscc_manager = llvm::CGSCCAnalysisManager { };
	auto MAM = llvm::ModuleAnalysisManager { };
	auto FAM = llvm::FunctionAnalysisManager { };

	PB.registerModuleAnalyses(MAM);
	PB.registerCGSCCAnalyses(cgscc_manager);
	PB.registerFunctionAnalyses(FAM);
	PB.registerLoopAnalyses(LAM);
	PB.crossRegisterProxies(LAM, FAM, cgscc_manager, MAM);

	llvm::FunctionPassManager FPM;

	// Form SSA out of local memory accesses after breaking apart aggregates into
	// scalars.
	FPM.addPass(llvm::SROAPass());

	// Catch trivial redundancies
	FPM.addPass(llvm::EarlyCSEPass(true /* Enable mem-ssa. */));

	//if (EnableKnowledgeRetention)
	FPM.addPass(llvm::AssumeSimplifyPass());
	FPM.addPass(llvm::SimplifyCFGPass());

	// Hoisting of scalars and load expressions.
	if (EnableGVNHoist)
		FPM.addPass(llvm::GVNHoistPass());

	// Global value numbering based sinking.
	if (EnableGVNSink) {
		FPM.addPass(llvm::GVNSinkPass());
		FPM.addPass(llvm::SimplifyCFGPass());
	}

	//if (EnableConstraintElimination)
	FPM.addPass(llvm::ConstraintEliminationPass());

	// Speculative execution if the target has divergent branches; otherwise nop.
	FPM.addPass(
			llvm::SpeculativeExecutionPass(/* OnlyIfDivergentTarget =*/true));

	// Optimize based on known information about branches, and cleanup afterward.
	FPM.addPass(llvm::JumpThreadingPass());
	FPM.addPass(llvm::CorrelatedValuePropagationPass());

	FPM.addPass(llvm::SimplifyCFGPass());
	FPM.addPass(llvm::InstCombinePass());
	FPM.addPass(llvm::AggressiveInstCombinePass());

	//invokePeepholeEPCallbacks(FPM, Level);

	// For PGO use pipeline, try to optimize memory intrinsics such as memcpy
	// using the size value profile. Don't perform this when optimizing for size.
	//if (PGOOpt && PGOOpt->Action == PGOOptions::IRUse &&
	//    !Level.isOptimizingForSize())
	//  FPM.addPass(llvm::PGOMemOPSizeOpt());

	//FPM.addPass(TailCallElimPass());
	FPM.addPass(llvm::SimplifyCFGPass());

	// Form canonically associated expression trees, and simplify the trees using
	// basic mathematical properties. For example, this will form (nearly)
	// minimal multiplication trees.
	FPM.addPass(llvm::ReassociatePass());

	// Add the primary loop simplification pipeline.
	// FIXME: Currently this is split into two loop pass pipelines because we run
	// some function passes in between them. These can and should be removed
	// and/or replaced by scheduling the loop pass equivalents in the correct
	// positions. But those equivalent passes aren't powerful enough yet.
	// Specifically, `SimplifyCFGPass` and `InstCombinePass` are currently still
	// used. We have `LoopSimplifyCFGPass` which isn't yet powerful enough yet to
	// fully replace `SimplifyCFGPass`, and the closest to the other we have is
	// `LoopInstSimplify`.
	llvm::LoopPassManager LPM1, LPM2;

	// Simplify the loop body. We do this initially to clean up after other loop
	// passes run, either when iterating on a loop or on inner loops with
	// implications on the outer loop.
	LPM1.addPass(llvm::LoopInstSimplifyPass());
	LPM1.addPass(llvm::LoopSimplifyCFGPass());

	// Try to remove as much code from the loop header as possible,
	// to reduce amount of IR that will have to be duplicated.
	// TODO: Investigate promotion cap for O1.
	LPM1.addPass(
			llvm::LICMPass(PTO.LicmMssaOptCap,
					PTO.LicmMssaNoAccForPromotionCap,
					/*AllowSpeculation=*/false));

	// Disable header duplication in loop rotation at -Oz.
	LPM1.addPass(llvm::LoopRotatePass(true));
	// TODO: Investigate promotion cap for O1.
	LPM1.addPass(
			llvm::LICMPass(PTO.LicmMssaOptCap,
					PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/true));
	LPM1.addPass(
			llvm::SimpleLoopUnswitchPass(
					/* NonTrivial */Level
							== llvm::OptimizationLevel::O3
							&& EnableO3NonTrivialUnswitching));
	// if (EnableLoopFlatten)
	//   LPM1.addPass(LoopFlattenPass());
	LPM2.addPass(llvm::LoopIdiomRecognizePass());
	LPM2.addPass(llvm::IndVarSimplifyPass());

	//for (auto &C : LateLoopOptimizationsEPCallbacks)
	//  C(LPM2, Level);

	LPM2.addPass(llvm::LoopDeletionPass());

	//if (EnableLoopInterchange)
	//LPM2.addPass(llvm::LoopInterchangePass());

	// Do not enable unrolling in PreLinkThinLTO phase during sample PGO
	// because it changes IR to makes profile annotation in back compile
	// inaccurate. The normal unroller doesn't pay attention to forced full unroll
	// attributes so we need to make sure and allow the full unroll pass to pay
	// attention to it.
	//if (Phase != ThinOrFullLTOPhase::ThinLTOPreLink || !PGOOpt ||
	//    PGOOpt->Action != PGOOptions::SampleUse)
	//  LPM2.addPass(LoopFullUnrollPass(Level.getSpeedupLevel(),
	//                                  /* OnlyWhenForced= */ !PTO.LoopUnrolling,
	//                                  PTO.ForgetAllSCEVInLoopUnroll));

	//for (auto &C : LoopOptimizerEndEPCallbacks)
	//  C(LPM2, Level);

	// We provide the opt remark emitter pass for LICM to use. We only need to do
	// this once as it is immutable.
	FPM.addPass(
			llvm::RequireAnalysisPass<llvm::OptimizationRemarkEmitterAnalysis,
					llvm::Function>());
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(std::move(LPM1),
	/*UseMemorySSA=*/true,
	/*UseBlockFrequencyInfo=*/true));
	FPM.addPass(
			llvm::SimplifyCFGPass(
					llvm::SimplifyCFGOptions().convertSwitchRangeToICmp(true)));
	FPM.addPass(llvm::InstCombinePass());

	// The loop passes in LPM2 (LoopIdiomRecognizePass, IndVarSimplifyPass,
	// LoopDeletionPass and LoopFullUnrollPass) do not preserve MemorySSA.
	// *All* loop passes must preserve it, in order to be able to use it.
	FPM.addPass(createFunctionToLoopPassAdaptor(std::move(LPM2),
	/*UseMemorySSA=*/false,
	/*UseBlockFrequencyInfo=*/false));

	// Delete small array after loop unroll.
	FPM.addPass(llvm::SROAPass());

	// The matrix extension can introduce large vector operations early, which can
	// benefit from running vector-combine early on.
	//  if (EnableMatrix)
	//    FPM.addPass(VectorCombinePass(/*ScalarizationOnly=*/true));

	// Eliminate redundancies.
	FPM.addPass(
			llvm::MergedLoadStoreMotionPass(llvm::MergedLoadStoreMotionOptions(
			/*SplitFooterBB=*/true)));
	//if (RunNewGVN)
	FPM.addPass(llvm::NewGVNPass());
	//else
	//  FPM.addPass(GVN());

	// Sparse conditional constant propagation.
	// FIXME: It isn't clear why we do this *after* loop passes rather than
	// before...
	FPM.addPass(llvm::SCCPPass());

	// Delete dead bit computations (instcombine runs after to fold away the dead
	// computations, and then ADCE will run later to exploit any new DCE
	// opportunities that creates).
	FPM.addPass(llvm::BDCEPass());

	// Run instcombine after redundancy and dead bit elimination to exploit
	// opportunities opened up by them.
	FPM.addPass(llvm::InstCombinePass());
	//invokePeepholeEPCallbacks(FPM, Level);

	// Re-consider control flow based optimizations after redundancy elimination,
	// redo DCE, etc.
	//  if (EnableDFAJumpThreading && Level.getSizeLevel() == 0)
	FPM.addPass(llvm::DFAJumpThreadingPass());

	FPM.addPass(llvm::JumpThreadingPass()); // segfauld on insert to internal set in non debug builds
	FPM.addPass(llvm::CorrelatedValuePropagationPass());

	// Finally, do an expensive DCE pass to catch all the dead code exposed by
	// the simplifications and basic cleanup after all the simplifications.
	// TODO: Investigate if this is too expensive.
	FPM.addPass(llvm::ADCEPass());

	// Specially optimize memory movement as it doesn't look like dataflow in SSA.
	FPM.addPass(llvm::MemCpyOptPass());

	FPM.addPass(llvm::DSEPass());
	FPM.addPass(
			llvm::createFunctionToLoopPassAdaptor(
					llvm::LICMPass(PTO.LicmMssaOptCap,
							PTO.LicmMssaNoAccForPromotionCap,
							/*AllowSpeculation=*/true),
					/*UseMemorySSA=*/true, /*UseBlockFrequencyInfo=*/true));

	//FPM.addPass(llvm::CoroElidePass());

//	for (auto &C : ScalarOptimizerLateEPCallbacks)
//		C(FPM, Level);

	FPM.addPass(llvm::SimplifyCFGPass(llvm::SimplifyCFGOptions() //
	.convertSwitchRangeToICmp(true) //
	.hoistCommonInsts(true) //
	.sinkCommonInsts(true)));
	FPM.addPass(llvm::InstCombinePass());
	//invokePeepholeEPCallbacks(FPM, Level);

	FPM.addPass(hwtHls::ExtractBitConcatAndSliceOpsPass());
	FPM.addPass(llvm::InstCombinePass()); // mostly for DCE for previous pass
	FPM.addPass(llvm::AggressiveInstCombinePass());
	//llvm::errs() << fn << "\n";
	FPM.addPass(hwtHls::BitwidthReductionPass());
	FPM.addPass(llvm::InstCombinePass()); // mostly for DCE for previous pass
	FPM.addPass(
			llvm::MergedLoadStoreMotionPass(llvm::MergedLoadStoreMotionOptions(
			/*SplitFooterBB=*/true)));
	// LowerSwitchPass
	//FPM.addPass(llvm::GVNHoistPass());
	//FPM.addPass(llvm::GVNSinkPass());
	FPM.addPass(
			llvm::SimplifyCFGPass(
					llvm::SimplifyCFGOptions().hoistCommonInsts(true).sinkCommonInsts(
							true)));
	//if (EnableCHR && Level == OptimizationLevel::O3 && PGOOpt
	//		&& (PGOOpt->Action == PGOOptions::IRUse
	//				|| PGOOpt->Action == PGOOptions::SampleUse))
	//	FPM.addPass(llvm::ControlHeightReductionPass());

	FPM.run(fn, FAM);

	//llvm::MachineFunctionAnalysisManager MFAM;
	//llvm::MachineFunctionPassManager MPM;
	//
	//if (auto e = MPM.run(*fn.getParent(), MFAM)) {
	//	throw std::runtime_error("Error during running MachineFunctionPassManager");
	//}

	//llvm::cl::ParseCommandLineOptions(argc, argv, "This is a small program to demo the LLVM CommandLine API");
	// use CodeGenPassBuilder once complete
	// :info: based on llc.cpp

	PM.add(MMIWP);
	// check for incompatible passes
	llvm::TargetPassConfig &TPC =
			*static_cast<llvm::LLVMTargetMachine&>(*TM).createPassConfig(PM);
	if (TPC.hasLimitedCodeGenPipeline()) {
		llvm::errs() << "run-pass cannot be used with "
				<< TPC.getLimitedCodeGenPipelineReason(" and ") << ".\n";
		throw std::runtime_error("run-pass cannot be used with ...");
	}

	PM.add(&TPC);

	// add passes which convert llvm::Function to llvm::MachineFunction
	if (TPC.addISelPasses())
		llvm_unreachable("Can not addISelPasses");
	TPC.printAndVerify("before addMachinePasses");
	TPC.addMachinePasses(); // add main bundle of Machine level optimizations
	PM.add(new hwtHls::GenericFpgaToNetlist(toNetlist));
	// place for custom machine passes
	TPC.printAndVerify("after addMachinePasses");
	TPC.setInitialized();
	//PM.add(llvm::createFreeMachineFunctionPass());
	PM.run(*fn.getParent());
}

llvm::MachineFunction* LlvmCompilationBundle::getMachineFunction(
		llvm::Function &fn) {
	auto &MMI = MMIWP->getMMI();
	// llvm::LoopAnalysis & LA = MMIWP->getAnalysis<llvm::LoopAnalysis>();
	return MMI.getMachineFunction(fn);
}

}
