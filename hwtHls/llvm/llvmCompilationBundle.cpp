#include <hwtHls/llvm/llvmCompilationBundle.h>

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
#include <llvm/Passes/StandardInstrumentations.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/CFGPrinter.h>
//#include <llvm/Transforms/IPO/PassManagerBuilder.h>
#include <llvm/Transforms/AggressiveInstCombine/AggressiveInstCombine.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Instrumentation/ControlHeightReduction.h>
#include <llvm/Transforms/IPO/StripDeadPrototypes.h>
#include <llvm/Transforms/IPO/StripSymbols.h>
#include <llvm/Transforms/IPO/ConstantMerge.h>
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
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>
#include <llvm/Transforms/Scalar/LoopUnrollAndJamPass.h>
#include <llvm/Transforms/Scalar/WarnMissedTransforms.h>
#include <llvm/Transforms/Scalar/LoopLoadElimination.h>
#include <llvm/Transforms/Scalar/AlignmentFromAssumptions.h>
#include <llvm/Transforms/Scalar/MergeICmps.h>
#include <llvm/Transforms/Vectorize/LoopVectorize.h>
#include <llvm/Transforms/Vectorize/SLPVectorizer.h>
#include <llvm/Transforms/Vectorize/VectorCombine.h>
#include <llvm/Transforms/Utils/AssumeBundleBuilder.h>
#include <llvm/Transforms/Utils.h>
#include <llvm/Transforms/Utils/Local.h>


#include <llvm/Target/TargetMachine.h>
//#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/CodeGen.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>

#include <hwtHls/llvm/targets/hwtFpgaTargetInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>
#include <hwtHls/llvm/Transforms/extractBitConcatAndSliceOpsPass.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass.h>
#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>
#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>
#include <hwtHls/llvm/Transforms/LoopUnrotatePass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>


namespace hwtHls {

const std::string LlvmCompilationBundle::TargetTriple = "hwtFpga-unknown-linux-gnu";
const std::string LlvmCompilationBundle::CPU = "model0";
const std::string LlvmCompilationBundle::Features = "model0";

LlvmCompilationBundle::LlvmCompilationBundle(const std::string &moduleName) :
		ctx(), strCtx(), module(new llvm::Module(strCtx.addStringRef(moduleName), ctx)),
		builder(ctx), main(nullptr), MMIWP(nullptr), VerifyEachPass(false), DebugPM(DebugLogging::None) {
	Target = &getTheHwtFpgaTarget(); //llvm::TargetRegistry::targets()[0];
	Level = llvm::OptimizationLevel::O3;
	EnableO3NonTrivialUnswitching = true;
	EnableGVNHoist = true;
	EnableGVNSink = true;

	llvm::TargetOptions opt;
	// useless for this target
	opt.XCOFFTracebackTable = false;
	// only GlobalISel implemented (No FastISel, SelectionDAGISel)
	opt.EnableGlobalISel = true;

	TPC = nullptr;
	auto RM = std::optional<llvm::Reloc::Model>();
	TM = Target->createTargetMachine(TargetTriple, CPU, Features, opt, RM);
	TM->setOptLevel(llvm::CodeGenOpt::Level::Aggressive);
	PTO = llvm::PipelineTuningOptions();
	llvm::LLVMTargetMachine &LLVMTM = static_cast<llvm::LLVMTargetMachine&>(*TM);
	MMIWP = new llvm::MachineModuleInfoWrapperPass(&LLVMTM);
	PrintPassOpts.Verbose = DebugPM == DebugLogging::Verbose;
	PrintPassOpts.SkipAnalyses = DebugPM == DebugLogging::Quiet;
}

void LlvmCompilationBundle::_initPassBuilder() {
	PB = std::make_unique<llvm::PassBuilder>(
		/*TargetMachine *TM = */TM,
		/* PipelineTuningOptions PTO = */PTO,
		/*Optional<PGOOptions> PGOOpt =*/std::nullopt,
		/*PassInstrumentationCallbacks *PIC =*/&PIC);
}

void LlvmCompilationBundle::addLlvmCliArgOccurence(const std::string & OptionName, unsigned pos, const std::string & ArgName, const std::string & ArgValue) {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto o = Map.find(OptionName);
	if (o == Map.end()) {
		if (OptionName == "debug-only") {
			throw std::runtime_error("debug-only LLVM cli option is available only in LLVM debug build");
		} else {
			throw std::runtime_error(std::string("Can not find LLVM cli option ") + OptionName);
		}
	}
	o->second->addOccurrence(pos, strCtx.addStringRef(ArgName), strCtx.addStringRef(ArgValue));
}


void LlvmCompilationBundle::runOpt(hwtHls::HwtFpgaToNetlist::ConvesionFnT toNetlistConversionFn) {
	assert(main && "a main function must be created before call of this function");

	auto &F = *main;
	// https://stackoverflow.com/questions/51934964/function-optimization-pass
	// @see PassBuilder::buildFunctionSimplificationPipeline

	F.getParent()->setDataLayout(TM->createDataLayout());

	auto LAM = llvm::LoopAnalysisManager { };
	auto CGAM = llvm::CGSCCAnalysisManager { };
	auto MAM = llvm::ModuleAnalysisManager { };
	auto FAM = llvm::FunctionAnalysisManager { };
	//VerifyEachPass = true;
	// PIC same as in llvm/toools/opt/NewPMDriver.cpp llvm::runPassPipeline()
	llvm::StandardInstrumentations SI(ctx, DebugPM != DebugLogging::None,
	                            VerifyEachPass, PrintPassOpts);
	SI.registerCallbacks(PIC, &FAM);
	_initPassBuilder();
	PB->registerModuleAnalyses(MAM);
	PB->registerCGSCCAnalyses(CGAM);
	PB->registerFunctionAnalyses(FAM);
	PB->registerLoopAnalyses(LAM);
	PB->crossRegisterProxies(LAM, FAM, CGAM, MAM);

	llvm::FunctionPassManager FPM;

	_addInitialNormalizationPasses(FPM);
	_addStreamOperationLoweringPasses(FPM);
	FPM.addPass(hwtHls::SimplifyCFG2Pass());

	// Hoisting of scalars and load expressions.
	if (EnableGVNHoist)
		FPM.addPass(llvm::GVNHoistPass());

	// Global value numbering based sinking.
	if (EnableGVNSink) {
		FPM.addPass(llvm::GVNSinkPass());
		FPM.addPass(hwtHls::SimplifyCFG2Pass());
	}

	// Speculative execution if the target has divergent branches; otherwise nop.
	FPM.addPass(
			llvm::SpeculativeExecutionPass(/* OnlyIfDivergentTarget =*/true));

	// Optimize based on known information about branches, and cleanup afterward.
	FPM.addPass(llvm::JumpThreadingPass());
	FPM.addPass(llvm::CorrelatedValuePropagationPass());

	FPM.addPass(hwtHls::SimplifyCFG2Pass());
	FPM.addPass(llvm::InstCombinePass());
	FPM.addPass(llvm::AggressiveInstCombinePass());

	//if (EnableConstraintElimination)
	FPM.addPass(llvm::ConstraintEliminationPass()); // hwtHls specific

	//if (!Level.isOptimizingForSize())
	//  FPM.addPass(LibCallsShrinkWrapPass());
    //
	//invokePeepholeEPCallbacks(FPM, Level);
    //
	//// For PGO use pipeline, try to optimize memory intrinsics such as memcpy
	//// using the size value profile. Don't perform this when optimizing for size.
	//if (PGOOpt && PGOOpt->Action == PGOOptions::IRUse &&
	//    !Level.isOptimizingForSize())
	//  FPM.addPass(PGOMemOPSizeOpt());
    //
	//FPM.addPass(TailCallElimPass());
	FPM.addPass(hwtHls::SimplifyCFG2Pass());

	// Form canonically associated expression trees, and simplify the trees using
	// basic mathematical properties. For example, this will form (nearly)
	// minimal multiplication trees.
	FPM.addPass(llvm::ReassociatePass());

	_addLoopPasses(FPM);
	_addVectorPasses(Level, FPM, false); // directly after loop passes

	_addCommonPasses(FPM);
	//invokePeepholeEPCallbacks(FPM, Level);

	FPM.addPass(hwtHls::ExtractBitConcatAndSliceOpsPass()); // hwtHls specific
	_addInstrCombinePasses(FPM);
	FPM.addPass(
			llvm::MergedLoadStoreMotionPass(llvm::MergedLoadStoreMotionOptions(
			/*SplitFooterBB=*/true))); // // hwtHls specific

	// LowerSwitchPass

	// :note: Profile data not yet available
	//if (EnableCHR && Level == OptimizationLevel::O3 && PGOOpt
	//		&& (PGOOpt->Action == PGOOptions::IRUse
	//				|| PGOOpt->Action == PGOOptions::SampleUse))
	//	FPM.addPass(llvm::ControlHeightReductionPass());
	_addVectorPasses(Level, FPM, true); // LTO like vector opt, after all IR opt, followed by final cleanup and machine passes
	FPM.addPass(
			hwtHls::SimplifyCFG2Pass(
					llvm::SimplifyCFGOptions()//
					.forwardSwitchCondToPhi(true)//
					.convertSwitchRangeToICmp(true)//
					.convertSwitchToLookupTable(true)//
					.needCanonicalLoops(false)//
					.hoistCommonInsts(true)//
					.sinkCommonInsts(true)//
					.bonusInstThreshold(1024)
	));

	FPM.addPass(llvm::DCEPass()); // because of convertSwitchToLookupTable=true
	FPM.addPass(hwtHls::SlicesMergePass());
	_addInstrCombinePasses(FPM);

	FPM.run(F, FAM);

	// module cleanup section
	llvm::ModulePassManager MPM;
	//if (!DeleteFn)
	//    MPM.addPass(llvm::GlobalDCEPass());
    //MPM.addPass(llvm::ExtractGVPass(Gvs, DeleteFn, KeepConstInit));
	MPM.addPass(llvm::ConstantMergePass());
    MPM.addPass(llvm::StripDeadDebugInfoPass());
    MPM.addPass(llvm::StripDeadPrototypesPass());
    MPM.run(*module, MAM);

    _addMachineCodegenPasses(toNetlistConversionFn);

	PM.run(*F.getParent());
}


void LlvmCompilationBundle::_addInitialNormalizationPasses(
		llvm::FunctionPassManager &FPM) {
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass());
	llvm::LoopPassManager LPM0;
	LPM0.addPass(hwtHls::LoopUnrotatePass());
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(std::move(LPM0),
			/*UseMemorySSA=*/ false,
			/*UseBlockFrequencyInfo=*/ false));
	// [fixme] LoopUnrotatePass probably breaks SE and TrivialSimplifyCFGPass forces to recompute it
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass()); // simplify trivial cases so IR is more easy to read
	// Form SSA out of local memory accesses after breaking apart aggregates into
	// scalars.
	FPM.addPass(hwtHls::SimplifyCFG2Pass(llvm::SimplifyCFGOptions().hoistCommonInsts(true)));

	FPM.addPass(hwtHls::SlicesToIndependentVariablesPass()); // hwtHls specific
	FPM.addPass(llvm::ADCEPass()); // hwtHls specific
	FPM.addPass(llvm::SROAPass(llvm::SROAOptions::ModifyCFG));
	// Catch trivial redundancies
	FPM.addPass(llvm::EarlyCSEPass(true /* Enable mem-ssa. */));
	//if (EnableKnowledgeRetention)
	FPM.addPass(llvm::AssumeSimplifyPass());

}

void LlvmCompilationBundle::_addStreamOperationLoweringPasses(
		llvm::FunctionPassManager &FPM) {
	// StreamLoopUnrollPass must be before StreamReadLoweringPass, StreamWriteLoweringPass
	// because if used correctly it reduces complexity of stream processing exponentially
	FPM.addPass(hwtHls::StreamLoopUnrollPass());
	FPM.addPass(hwtHls::StreamReadLoweringPass());
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass());
	FPM.addPass(hwtHls::StreamWriteLoweringPass());
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass());
}

void LlvmCompilationBundle::_addCommonPasses(llvm::FunctionPassManager &FPM) {
	// Delete small array after loop unroll.
	FPM.addPass(llvm::SROAPass(llvm::SROAOptions::ModifyCFG));
	// The matrix extension can introduce large vector operations early, which can
	// benefit from running vector-combine early on.
	//  if (EnableMatrix)
	//    FPM.addPass(VectorCombinePass(/*ScalarizationOnly=*/true));
	// Eliminate redundancies.
	FPM.addPass(
			llvm::MergedLoadStoreMotionPass(llvm::MergedLoadStoreMotionOptions(/*SplitFooterBB=*/
			true)));
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
	FPM.addPass(llvm::JumpThreadingPass()); // segfault on insert to internal set in non debug builds
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
							PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
							true),
							/*UseMemorySSA=*/true,
							/*UseBlockFrequencyInfo=*/true));
	//FPM.addPass(llvm::CoroElidePass());
	//	for (auto &C : ScalarOptimizerLateEPCallbacks)
	//		C(FPM, Level);
	FPM.addPass(
			hwtHls::SimplifyCFG2Pass(
					llvm::SimplifyCFGOptions().convertSwitchRangeToICmp(true).hoistCommonInsts(
							true).sinkCommonInsts(true)));
	FPM.addPass(llvm::InstCombinePass());
}

void LlvmCompilationBundle::_addInstrCombinePasses(llvm::FunctionPassManager &FPM) {
	FPM.addPass(llvm::InstCombinePass()); // hwtHls specific
	FPM.addPass(llvm::AggressiveInstCombinePass()); // hwtHls specific
	FPM.addPass(hwtHls::BitwidthReductionPass());
	FPM.addPass(llvm::InstCombinePass()); // hwtHls specific
}

void LlvmCompilationBundle::_addLoopPasses(llvm::FunctionPassManager &FPM) {
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
			llvm::LICMPass(PTO.LicmMssaOptCap, PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
			false));
	// Disable header duplication in loop rotation at -Oz.
	LPM1.addPass(llvm::LoopRotatePass(false, /*PrepareForLTO*/
	false));
	// TODO: Investigate promotion cap for O1.
	LPM1.addPass(
			llvm::LICMPass(PTO.LicmMssaOptCap, PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
			true));
	LPM1.addPass(llvm::SimpleLoopUnswitchPass(/* NonTrivial */
	Level == llvm::OptimizationLevel::O3 && EnableO3NonTrivialUnswitching));
	// if (EnableLoopFlatten)
	//   LPM1.addPass(llvm::LoopFlattenPass());
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
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(std::move(LPM1), /*UseMemorySSA=*/
	true, /*UseBlockFrequencyInfo=*/
	true));
	FPM.addPass(
			hwtHls::SimplifyCFG2Pass(
					llvm::SimplifyCFGOptions().convertSwitchRangeToICmp(true)));

	FPM.addPass(llvm::InstCombinePass());
	// The loop passes in LPM2 (LoopIdiomRecognizePass, IndVarSimplifyPass,
	// LoopDeletionPass and LoopFullUnrollPass) do not preserve MemorySSA.
	// *All* loop passes must preserve it, in order to be able to use it.
	FPM.addPass(createFunctionToLoopPassAdaptor(std::move(LPM2), /*UseMemorySSA=*/
	false, /*UseBlockFrequencyInfo=*/
	false));
}

void LlvmCompilationBundle::_addVectorPasses(llvm::OptimizationLevel Level,
		llvm::FunctionPassManager &FPM, bool IsFullLTO) {
	// based on PassBuilder::addVectorPasses
	FPM.addPass(
			llvm::LoopVectorizePass(
					llvm::LoopVectorizeOptions(!PTO.LoopInterleaving,
							!PTO.LoopVectorization)));
	if (IsFullLTO) {
		// The vectorizer may have significantly shortened a loop body; unroll
		// again. Unroll small loops to hide loop backedge latency and saturate any
		// parallel execution resources of an out-of-order processor. We also then
		// need to clean up redundancies and loop invariant code.
		// FIXME: It would be really good to use a loop-integrated instruction
		// combiner for cleanup here so that the unrolling and LICM can be pipelined
		// across the loop nests.
		// We do UnrollAndJam in a separate LPM to ensure it happens before unroll
		if (PTO.LoopUnrolling)
			FPM.addPass(
					llvm::createFunctionToLoopPassAdaptor(
							llvm::LoopUnrollAndJamPass(
									Level.getSpeedupLevel())));
		FPM.addPass(
				llvm::LoopUnrollPass(
						llvm::LoopUnrollOptions(Level.getSpeedupLevel(), /*OnlyWhenForced=*/
						!PTO.LoopUnrolling, PTO.ForgetAllSCEVInLoopUnroll)));
		FPM.addPass(llvm::WarnMissedTransformationsPass());
	}

	if (!IsFullLTO) {
		// Eliminate loads by forwarding stores from the previous iteration to loads
		// of the current iteration.
		FPM.addPass(llvm::LoopLoadEliminationPass());
	}
	// Cleanup after the loop optimization passes.
	FPM.addPass(llvm::InstCombinePass());

	if (Level.getSpeedupLevel() > 1) { //  && ExtraVectorizerPasses
		llvm::ExtraVectorPassManager ExtraPasses;
		// At higher optimization levels, try to clean up any runtime overlap and
		// alignment checks inserted by the vectorizer. We want to track correlated
		// runtime checks for two inner loops in the same outer loop, fold any
		// common computations, hoist loop-invariant aspects out of any outer loop,
		// and unswitch the runtime checks if possible. Once hoisted, we may have
		// dead (or speculatable) control flows or more combining opportunities.
		ExtraPasses.addPass(llvm::EarlyCSEPass());
		ExtraPasses.addPass(llvm::CorrelatedValuePropagationPass());
		ExtraPasses.addPass(llvm::InstCombinePass());
		llvm::LoopPassManager LPM;
		LPM.addPass(
				llvm::LICMPass(PTO.LicmMssaOptCap,
						PTO.LicmMssaNoAccForPromotionCap,
						/*AllowSpeculation=*/true));
		LPM.addPass(
				llvm::SimpleLoopUnswitchPass(
						/* NonTrivial */Level == llvm::OptimizationLevel::O3));
		ExtraPasses.addPass(
				llvm::RequireAnalysisPass<
						llvm::OptimizationRemarkEmitterAnalysis, llvm::Function>());
		ExtraPasses.addPass(
				createFunctionToLoopPassAdaptor(std::move(LPM), /*UseMemorySSA=*/
						true,
						/*UseBlockFrequencyInfo=*/true));
		ExtraPasses.addPass(
				hwtHls::SimplifyCFG2Pass(
						llvm::SimplifyCFGOptions()//
						.convertSwitchRangeToICmp(true)));
		ExtraPasses.addPass(llvm::InstCombinePass());
		FPM.addPass(std::move(ExtraPasses));
	}

	// Now that we've formed fast to execute loop structures, we do further
	// optimizations. These are run afterward as they might block doing complex
	// analyses and transforms such as what are needed for loop vectorization.

	// Cleanup after loop vectorization, etc. Simplification passes like CVP and
	// GVN, loop transforms, and others have already run, so it's now better to
	// convert to more optimized IR using more aggressive simplify CFG options.
	// The extra sinking transform can create larger basic blocks, so do this
	// before SLP vectorization.
	FPM.addPass(hwtHls::SimplifyCFG2Pass(llvm::SimplifyCFGOptions()
	                                .forwardSwitchCondToPhi(true)
	                                .convertSwitchRangeToICmp(true)
	                                //.convertSwitchToLookupTable(true)
	                                .needCanonicalLoops(false)
	                                .hoistCommonInsts(true)
	                                .sinkCommonInsts(true)));

	if (IsFullLTO) {
		FPM.addPass(llvm::SCCPPass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(llvm::BDCEPass());
	}

	// Optimize parallel scalar instruction chains into SIMD instructions.
	if (PTO.SLPVectorization) {
		FPM.addPass(llvm::SLPVectorizerPass());
		if (Level.getSpeedupLevel() > 1) { // && ExtraVectorizerPasses
			FPM.addPass(llvm::EarlyCSEPass());
		}
	}
	// Enhance/cleanup vector code.
	FPM.addPass(llvm::VectorCombinePass());

	if (!IsFullLTO) {
		FPM.addPass(llvm::InstCombinePass());
		// Unroll small loops to hide loop backedge latency and saturate any
		// parallel execution resources of an out-of-order processor. We also then
		// need to clean up redundancies and loop invariant code.
		// FIXME: It would be really good to use a loop-integrated instruction
		// combiner for cleanup here so that the unrolling and LICM can be pipelined
		// across the loop nests.
		// We do UnrollAndJam in a separate LPM to ensure it happens before unroll
		if (PTO.LoopUnrolling) { // EnableUnrollAndJam &&
			FPM.addPass(
					llvm::createFunctionToLoopPassAdaptor(
							llvm::LoopUnrollAndJamPass(
									Level.getSpeedupLevel())));
		}
		FPM.addPass(
				llvm::LoopUnrollPass(
						llvm::LoopUnrollOptions(Level.getSpeedupLevel(), /*OnlyWhenForced=*/
								!PTO.LoopUnrolling,
								PTO.ForgetAllSCEVInLoopUnroll)));
		FPM.addPass(llvm::WarnMissedTransformationsPass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(
				llvm::RequireAnalysisPass<
						llvm::OptimizationRemarkEmitterAnalysis, llvm::Function>());
		FPM.addPass(
				createFunctionToLoopPassAdaptor(
						llvm::LICMPass(PTO.LicmMssaOptCap,
								PTO.LicmMssaNoAccForPromotionCap,
								/*AllowSpeculation=*/true),
						/*UseMemorySSA=*/true, /*UseBlockFrequencyInfo=*/true));
	}

	// Now that we've vectorized and unrolled loops, we may have more refined
	// alignment information, try to re-derive it here.
	FPM.addPass(llvm::AlignmentFromAssumptionsPass());

	if (IsFullLTO)
		FPM.addPass(llvm::InstCombinePass());
}

void LlvmCompilationBundle::_addMachineCodegenPasses(
		hwtHls::HwtFpgaToNetlist::ConvesionFnT &toNetlistConversionFn) {
	//llvm::MachineFunctionAnalysisManager MFAM;
	//llvm::MachineFunctionPassManager MPM;
	//
	//if (auto e = MPM.run(*fn.getParent(), MFAM)) {
	//	throw std::runtime_error("Error during running MachineFunctionPassManager");
	//}

	// use CodeGenPassBuilder once complete

	// :info: based on llc.cpp
	PM.add(MMIWP);

	// check for incompatible passes
	TPC = static_cast<llvm::HwtFpgaTargetPassConfig*>(static_cast<llvm::LLVMTargetMachine&>(*TM).createPassConfig(
			PM));
	// :note: we can not use pass constructor to pass toNetlistConversionFn because
	//        because constructor must be callable without arguments because of INITIALIZE_PASS macros
	// :note: we can not call pass explicitly after PM.run() because addRequired/getAnalysis will not work
	TPC->toNetlistConversionFn = &toNetlistConversionFn;
	if (TPC->hasLimitedCodeGenPipeline()) {
		llvm::errs() << "run-pass cannot be used with " << TPC->getLimitedCodeGenPipelineReason(" and ") << ".\n";
		throw std::runtime_error("run-pass cannot be used with ...");
	}
	// PM.add(llvm::createCFGPrinterLegacyPassPass()); //llvm::CFGPrinterPass());

	PM.add(TPC);

	// add passes which convert llvm::Function to llvm::MachineFunction
	if (TPC->addISelPasses())
		llvm_unreachable("Can not addISelPasses");
	TPC->printAndVerify("before addMachinePasses");
	TPC->addMachinePasses(); // add main bundle of Machine level optimizations
	// place for custom machine passes
	TPC->printAndVerify("after addMachinePasses");
	TPC->setInitialized();

	//PM.add(llvm::createFreeMachineFunctionPass());
}

llvm::MachineFunction* LlvmCompilationBundle::getMachineFunction(llvm::Function &fn) {
	auto &MMI = MMIWP->getMMI();
	return MMI.getMachineFunction(fn);
}

llvm::MachineModuleInfo * LlvmCompilationBundle::getMachineModuleInfo() {
	return &MMIWP->getMMI();
}

}
