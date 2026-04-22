
#include <hwtHls/llvm/llvmCompilationBundle.h>

#include <memory>
#include <string>

#include <llvm/ADT/APInt.h>
#include <llvm/ADT/APSInt.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/Analysis/CFGPrinter.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassTimingInfo.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Pass.h>
#include <llvm/Passes/StandardInstrumentations.h>
// #include <llvm/Transforms/IPO/PassManagerBuilder.h>
#include <llvm/Transforms/AggressiveInstCombine/AggressiveInstCombine.h>
#include <llvm/Transforms/IPO/ConstantMerge.h>
#include <llvm/Transforms/IPO/StripDeadPrototypes.h>
#include <llvm/Transforms/IPO/StripSymbols.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Instrumentation/ControlHeightReduction.h>
#include <llvm/Transforms/Scalar.h>
#include <llvm/Transforms/Scalar/Reassociate.h>
// #include <llvm/Transforms/Scalar/NewGVN.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/Transforms/Scalar/AlignmentFromAssumptions.h>
#include <llvm/Transforms/Scalar/BDCE.h>
#include <llvm/Transforms/Scalar/ConstraintElimination.h>
#include <llvm/Transforms/Scalar/CorrelatedValuePropagation.h>
#include <llvm/Transforms/Scalar/DCE.h>
#include <llvm/Transforms/Scalar/DFAJumpThreading.h>
#include <llvm/Transforms/Scalar/DeadStoreElimination.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/Scalar/GVN.h>
#include <llvm/Transforms/Scalar/IndVarSimplify.h>
#include <llvm/Transforms/Scalar/JumpThreading.h>
#include <llvm/Transforms/Scalar/LICM.h>
#include <llvm/Transforms/Scalar/LoopDeletion.h>
#include <llvm/Transforms/Scalar/LoopDistribute.h>
#include <llvm/Transforms/Scalar/LoopFuse.h>
#include <llvm/Transforms/Scalar/LoopIdiomRecognize.h>
#include <llvm/Transforms/Scalar/LoopInstSimplify.h>
#include <llvm/Transforms/Scalar/LoopLoadElimination.h>
#include <llvm/Transforms/Scalar/LoopRotation.h>
#include <llvm/Transforms/Scalar/LoopSimplifyCFG.h>
#include <llvm/Transforms/Scalar/LoopUnrollAndJamPass.h>
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>
#include <llvm/Transforms/Scalar/MemCpyOptimizer.h>
#include <llvm/Transforms/Scalar/MergeICmps.h>
#include <llvm/Transforms/Scalar/MergedLoadStoreMotion.h>
#include <llvm/Transforms/Scalar/SCCP.h>
#include <llvm/Transforms/Scalar/SROA.h>
#include <llvm/Transforms/Scalar/SimpleLoopUnswitch.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>
#include <llvm/Transforms/Scalar/SpeculativeExecution.h>
#include <llvm/Transforms/Scalar/WarnMissedTransforms.h>
#include <llvm/Transforms/Utils.h>
#include <llvm/Transforms/Utils/AssumeBundleBuilder.h>
#include <llvm/Transforms/Utils/CountVisits.h>
#include <llvm/Transforms/Utils/FixIrreducible.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Utils/LowerSwitch.h>
#include <llvm/Transforms/Utils/UnifyFunctionExitNodes.h>
#include <llvm/Transforms/Vectorize/LoopVectorize.h>
#include <llvm/Transforms/Vectorize/SLPVectorizer.h>
#include <llvm/Transforms/Vectorize/VectorCombine.h>
// #include <llvm/Support/TargetSelect.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/Support/CodeGen.h>

#include <hwtHls/llvm/Transforms/BitcountMergePass.h>
#include <hwtHls/llvm/Transforms/HFloatTmpLoweringPass.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass.h>
#include <hwtHls/llvm/Transforms/ICmpToOnlyEqLtLePass.h>
#include <hwtHls/llvm/Transforms/IoLowerAxiMMPass.h>
#include <hwtHls/llvm/Transforms/LoopAddLatchPass.h>
#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass.h>
#include <hwtHls/llvm/Transforms/LoopRotationNormalizationPass.h>
#include <hwtHls/llvm/Transforms/ProfMetadataAddDummy.h>
#include <hwtHls/llvm/Transforms/ProfMetadataRmDummy.h>
#include <hwtHls/llvm/Transforms/PromoteAllocaToGlobalPass.h>
#include <hwtHls/llvm/Transforms/PruneLoopPhiDeadIncomingValuesPass/PruneLoopPhiDeadIncomingValuesPass.h>
#include <hwtHls/llvm/Transforms/ReconfigureHwtFpgaTTIPass.h>
#include <hwtHls/llvm/Transforms/RomExtractPass.h>
#include <hwtHls/llvm/Transforms/SelectPruningPass.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/StreamSegmentLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/StripAssumePass.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractPass.h>
#include <hwtHls/llvm/Transforms/TmpAllocaLoweringPass.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>
#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>
#include <hwtHls/llvm/Transforms/extractBitConcatAndSliceOpsPass.h>
#include <hwtHls/llvm/Transforms/overwriteBlockNamesPass.h>
#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>
#include <hwtHls/llvm/llvmCompilationBundleORE.h>
#include <hwtHls/llvm/llvmHwtHlsInstrumentation.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

namespace hwtHls {

void LlvmCompilationBundle::_registerHwtHlsPasses() {
	__registerHwtHlsPasses<hwtHls::BitwidthReductionPass,			   //
						   hwtHls::BitcountMergePass,				   //
						   hwtHls::HwtHlsInstCombinePass,			   //
						   hwtHls::ThreadExtractPass,				   //
						   hwtHls::ThreadExtractIoFsmPass,			   //
						   hwtHls::TmpAllocaLoweringPass,			   //
						   hwtHls::SlicesToIndependentVariablesPass,   //
						   hwtHls::ExtractBitConcatAndSliceOpsPass,	   //
						   hwtHls::HFloatTmpLoweringPass,			   //
						   hwtHls::ICmpToOnlyEqLtLePass,			   //
						   hwtHls::IoLowerAxiMMPass,				   //
						   hwtHls::LoopAddLatchPass,				   //
						   hwtHls::LoopFlattenUsingIfPass,			   //
						   hwtHls::LoopRotationNormalizationPass,	   //
						   hwtHls::OverwriteBlockNamesPass,			   //
						   hwtHls::ProfMetadataAddDummy,			   //
						   hwtHls::ProfMetadataRmDummy,				   //
						   hwtHls::PromoteAllocaToGlobalPass,		   //
						   hwtHls::PruneLoopPhiDeadIncomingValuesPass, //
						   hwtHls::ReconfigureHwtFpgaTTIPass,		   //
						   hwtHls::RomExtractPass,					   //
						   hwtHls::SelectPruningPass,				   //
						   hwtHls::StripAssumePass,					   //
						   hwtHls::HwtHlsSimplifyCFGPass,			   //
						   hwtHls::TrivialSimplifyCFGPass,			   //
						   hwtHls::HwtHlsInstCombinePass,			   //
						   hwtHls::SlicesMergePass,					   //
						   hwtHls::StreamReadLoweringPass,			   //
						   hwtHls::StreamWriteLoweringPass,			   //
						   hwtHls::StreamLoopUnrollPass,			   //
						   hwtHls::StreamSegmentLoopUnrollPass,		   //
						   void>();
}

struct HwtFpgaAllowVolatileMemOpDuplication {
	llvm::TargetMachine *TM;
	llvm::FunctionPassManager &FPM;
	HwtFpgaAllowVolatileMemOpDuplication(llvm::TargetMachine *TM,
										 llvm::FunctionPassManager &FPM) :
		TM(TM), FPM(FPM) {
		FPM.addPass(hwtHls::ReconfigureHwtFpgaTTIPass(TM, true));
	}
	~HwtFpgaAllowVolatileMemOpDuplication() {
		FPM.addPass(hwtHls::ReconfigureHwtFpgaTTIPass(TM, false));
	}
};

void LlvmCompilationBundle::runOpt(
	hwtHls::HwtFpgaToNetlist::ConvesionFnT toNetlistConversionFn,
	std::function<void(llvm::ModulePassManager &)> addExtraModulePasses) {
	if (!PB) {
		_initPassBuilder();
	} else {
		_llvmCliOpts_apply();
	}
	// https://stackoverflow.com/questions/51934964/function-optimization-pass
	// @see PassBuilder::buildFunctionSimplificationPipeline
	llvm::ModulePassManager MPM;
	llvm::FunctionPassManager FPM_initial;
	if (llvm::AreStatisticsEnabled())
		FPM_initial.addPass(llvm::CountVisitsPass());
	_addInitialNormalizationPasses(FPM_initial);
	_addStreamOperationLoweringPasses(FPM_initial);

	MPM.addPass(
		llvm::createModuleToFunctionPassAdaptor(std::move(FPM_initial)));
	MPM.addPass(hwtHls::ThreadExtractIoFsmPass());

	llvm::FunctionPassManager FPM;
	if (llvm::
			AreStatisticsEnabled()) // based on
									// PassBuilder::buildFunctionSimplificationPipeline
		FPM.addPass(llvm::CountVisitsPass());
	// Hoisting of scalars and load expressions.
	if (EnableGVNHoist)
		FPM.addPass(llvm::GVNHoistPass());

	// Global value numbering based sinking.
	if (EnableGVNSink) {
		FPM.addPass(llvm::GVNSinkPass());
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());
	}

	// Speculative execution if the target has divergent branches; otherwise
	// nop.
	FPM.addPass(
		llvm::SpeculativeExecutionPass(/* OnlyIfDivergentTarget =*/true));

	// Optimize based on known information about branches, and cleanup
	// afterward.
	FPM.addPass(llvm::JumpThreadingPass());
	FPM.addPass(llvm::CorrelatedValuePropagationPass());

	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());
	_addInstrCombinePasses(FPM, /*bitwidthReduction*/ false, /*selectPruning*/
						   false);

	// if (EnableConstraintElimination)
	FPM.addPass(llvm::ConstraintEliminationPass()); // hwtHls specific

	// if (!Level.isOptimizingForSize())
	//   FPM.addPass(LibCallsShrinkWrapPass());
	//
	// invokePeepholeEPCallbacks(FPM, Level);
	//
	//// For PGO use pipeline, try to optimize memory intrinsics such as memcpy
	//// using the size value profile. Don't perform this when optimizing for
	///size.
	// if (PGOOpt && PGOOpt->Action == PGOOptions::IRUse &&
	//     !Level.isOptimizingForSize())
	//   FPM.addPass(PGOMemOPSizeOpt());
	//
	// FPM.addPass(TailCallElimPass());
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());

	// Form canonically associated expression trees, and simplify the trees
	// using basic mathematical properties. For example, this will form (nearly)
	// minimal multiplication trees.
	FPM.addPass(llvm::ReassociatePass());

	_addLoopPasses(FPM);
	_addVectorPasses(Level, FPM, false); // directly after loop passes
	_addCommonPasses(FPM);
	// invokePeepholeEPCallbacks(FPM, Level);

	FPM.addPass(hwtHls::ExtractBitConcatAndSliceOpsPass()); // hwtHls specific
	_addInstrCombinePasses(FPM);
	FPM.addPass(
		llvm::MergedLoadStoreMotionPass(llvm::MergedLoadStoreMotionOptions(
			/*SplitFooterBB=*/true))); // // hwtHls specific

	// LowerSwitchPass

	// :note: Profile data not yet available
	// if (EnableCHR && Level == OptimizationLevel::O3 && PGOOpt
	//		&& (PGOOpt->Action == PGOOptions::IRUse
	//				|| PGOOpt->Action == PGOOptions::SampleUse))
	//	FPM.addPass(llvm::ControlHeightReductionPass());
	_addVectorPasses(Level, FPM,
					 true); // LTO like vector opt, after all IR opt, followed
							// by final cleanup and machine passes
	{
		auto simplifyCfgOpts =
			hwtHls::HwtHlsSimplifyCFGOptions()	  //
				.forwardSwitchCondToPhi(true)	  //
				.convertSwitchRangeToICmp(true)	  //
				.convertSwitchToLookupTable(true) //
				.needCanonicalLoops(
					false) // :attention: conversion back to canonical loops
						   // will spawn new loops if loop header has phi and
						   // more than 2 predecessors
				.hoistCommonInsts(true) //
				.sinkCommonInsts(true)	//
				.hoistCommonInsts(true) //
				.bonusInstThreshold(1024);
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}
	FPM.addPass(llvm::DCEPass()); // because of convertSwitchToLookupTable=true
	FPM.addPass(hwtHls::SlicesMergePass());
	FPM.addPass(hwtHls::PruneLoopPhiDeadIncomingValuesPass());

	_addInstrCombinePasses(FPM,
						   /*bitwidthReduction*/ true, /*selectPruning*/ true,
						   /*llvmInstrCombine*/ true,
						   /*streamReadEoFThreading*/ false,
						   /*hwtHlsFpInstrCombine*/ true);
	FPM.addPass(hwtHls::PromoteAllocaToGlobalPass());
	FPM.addPass(hwtHls::HFloatTmpLoweringPass());
	_addInstrCombinePasses(FPM,
						   /*bitwidthReduction*/ true, /*selectPruning*/ true,
						   /*llvmInstrCombine*/ true,
						   /*streamReadEoFThreading*/ false,
						   /*hwtHlsFpInstrCombine*/ true);
	// FPM.addPass(hwtHls::DumpAndExitPass(true, false, "dump.dot"));
	FPM.addPass(llvm::FixIrreduciblePass()); // loops needs to have single entry
	// FPM.run(F, *FAM);
	MPM.addPass(llvm::createModuleToFunctionPassAdaptor(std::move(FPM)));
	// if (!DeleteFn)
	//     MPM.addPass(llvm::GlobalDCEPass());
	// MPM.addPass(llvm::ExtractGVPass(Gvs, DeleteFn, KeepConstInit));
	addExtraModulePasses(MPM);
	MPM.addPass(llvm::ConstantMergePass());
	// MPM.addPass(hwtHls::LoopMarkStatelessPrequelPass());
	// MPM.addPass(hwtHls::LoopMarkStatelessSequelPass());
	MPM.addPass(hwtHls::ThreadExtractPass());
	MPM.addPass(llvm::createModuleToFunctionPassAdaptor(
		hwtHls::HwtHlsSimplifyCFGPass())); // ThreadExtractPass may create
										   // trivially mergable blocks
	MPM.addPass(llvm::StripDeadDebugInfoPass());
	MPM.addPass(llvm::StripDeadPrototypesPass());
	MPM.addPass(hwtHls::ProfMetadataRmDummy());
	//MPM.addPass(llvm::FixIrreduciblePass());
	//MPM.addPass(llvm::UnifyLoopExitsPass());
	MPM.run(*module, *MAM);
	_tryToFindMain();
	// main function may mutate in ThreadExtractPass
	// module cleanup section

	_addMachineCodegenPasses(toNetlistConversionFn);

	PM.run(*module);
	
	llvm::ModulePassManager MPM2;
	//MPM2.addPass(llvm::createModuleToFunctionPassAdaptor(hwtHls::DumpAndExitPass(
	//	true, false, "tmp/after._addMachineCodegenPasses.dot")));
	MPM2.run(*module, *MAM);
	
	// from llvm/lib/LTO/LTOCodeGenerator.cpp
	// If statistics were requested, save them to the specified file or
	// print them out after codegen.
	// if (StatsFile)
	//  PrintStatisticsJSON(StatsFile->os());
	// else
	if (llvm::AreStatisticsEnabled()) {
		llvm::PrintStatistics();
	}
	if (RemarksFile) {
		RemarksFile->keep();
		RemarksFile->os().flush();
	}
	SI.reset(); // to force dump of stats and timings new PassManager (IR)
	llvm::reportAndResetTimings(); // :note: only for legacy PassManger (MIR)
}

void LlvmCompilationBundle::_tryToFindMain() {
	std::optional<llvm::Function *> mainFn;
	for (auto &F : *module) {
		if (F.isDeclaration())
			continue;
		if (mainFn.has_value())
			mainFn = nullptr;
		else
			mainFn = &F;
	}
	if (!mainFn.has_value())
		mainFn = nullptr;
	main = mainFn.value();
}

void LlvmCompilationBundle::runExprOpt() {
	_runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		FPM.addPass(llvm::EarlyCSEPass());
		// FPM.addPass(hwtHls::BitwidthReductionPass());
		FPM.addPass(llvm::CorrelatedValuePropagationPass());
		FPM.addPass(llvm::AggressiveInstCombinePass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
		FPM.addPass(hwtHls::SelectPruningPass());
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(llvm::EarlyCSEPass());
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
		// FPM.addPass(hwtHls::SlicesMergePass());
		FPM.addPass(hwtHls::ICmpToOnlyEqLtLePass());
		FPM.addPass(hwtHls::StripAssumePass());
		FPM.addPass(llvm::DCEPass());
	});
}

void LlvmCompilationBundle::_addInitialNormalizationPasses(
	llvm::FunctionPassManager &FPM) {
	FPM.addPass(hwtHls::ProfMetadataAddDummy());
	FPM.addPass(llvm::DCEPass());
	FPM.addPass(hwtHls::TmpAllocaLoweringPass());
	// FPM.addPass(hwtHls::DumpAndExitPass(true, true, "dump.dot"));
	// FPM.addPass(hwtHls::OverwriteBlockNamesPass());
	// FPM.addPass(hwtHls::TrivialSimplifyCFGPass(true));
	llvm::LoopPassManager LPM0;
	// it is important that it is done before LoopFlattenUsingIfPass
	// otherwise hard to anlyze phis for pointers may appear for nested mem
	// allocas
	FPM.addPass(hwtHls::PromoteAllocaToGlobalPass());
	LPM0.addPass(hwtHls::LoopRotationNormalizationPass(
		0)); // normalize to rotated form, unrotate loop with costly header
	bool debugUse_BFI_BPI = false;
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
		std::move(LPM0),
		/*UseMemorySSA=*/false,
		/*UseBlockFrequencyInfo=*/debugUse_BFI_BPI,
		/*UseBranchProbabilityInfo=*/debugUse_BFI_BPI));

	FPM.addPass(hwtHls::TrivialSimplifyCFGPass(
		true, false)); // simplify trivial cases so IR is more easy to read
	llvm::LoopPassManager
		LPM0_1; // again the LoopRotationNormalizationPass because some patterns
				// were not recognized because of redundant blocks
	LPM0_1.addPass(hwtHls::LoopRotationNormalizationPass(10000));
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
		std::move(LPM0_1),
		/*UseMemorySSA=*/false,
		/*UseBlockFrequencyInfo=*/debugUse_BFI_BPI,
		/*UseBranchProbabilityInfo=*/debugUse_BFI_BPI));

	llvm::LoopPassManager LPM1;
	LPM1.addPass(hwtHls::LoopFlattenUsingIfPass());
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
		std::move(LPM1),
		/*UseMemorySSA=*/false,
		/*UseBlockFrequencyInfo=*/debugUse_BFI_BPI,
		/*UseBranchProbabilityInfo=*/debugUse_BFI_BPI));

	// [fixme] LoopUnrotatePass probably breaks SE and TrivialSimplifyCFGPass
	// forces to recompute it
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass(
		true, false)); // simplify trivial cases so IR is more easy to read
	FPM.addPass(llvm::UnifyFunctionExitNodesPass()); // llvm mergereturn
	// Form SSA out of local memory accesses after breaking apart aggregates
	// into scalars.
	{
		auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions() //
								   .hoistCommonInsts(true)		  //
								   .setHoistCheapInsts(true)	  //
			;
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}
	FPM.addPass(hwtHls::SlicesToIndependentVariablesPass()); // hwtHls specific
	FPM.addPass(llvm::ADCEPass());							 // hwtHls specific
	FPM.addPass(llvm::SROAPass(llvm::SROAOptions::ModifyCFG));
	// Catch trivial redundancies
	FPM.addPass(llvm::EarlyCSEPass(true /* Enable mem-ssa. */));
	// if (EnableKnowledgeRetention)
	FPM.addPass(llvm::AssumeSimplifyPass());
}

void LlvmCompilationBundle::_addStreamOperationLoweringPasses(
	llvm::FunctionPassManager &FPM) {
	// StreamLoopUnrollPass must be before StreamReadLoweringPass,
	// StreamWriteLoweringPass because if used correctly it reduces complexity
	// of stream processing exponentially
	_addInstrCombinePasses(FPM, false, false, false);
	FPM.addPass(hwtHls::StreamLoopUnrollPass());

	// :note: if SwitchReduceRange is allowed the LVI is not able to recognize
	// expressions generated by it (llvm-18)
	//  the LVI is important for stream related transformations as pruning of
	//  viable options for offset in stream must work perfectly to avoid code
	//  explosions
	auto SimplifyCfgOpts =
		hwtHls::HwtHlsSimplifyCFGOptions().setSwitchReduceRange(false);

	FPM.addPass(hwtHls::TrivialSimplifyCFGPass(true, false));
	// FPM.addPass(hwtHls::DumpAndExitPass(false, false,
	// "tmp/StreamLoopUnrollPass.1.dot", true));
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(SimplifyCfgOpts));
	// FPM.addPass(hwtHls::DumpAndExitPass(false, true,
	// "tmp/StreamLoopUnrollPass.2.dot", true));
	_addInstrCombinePasses(FPM, false, false, false);
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(SimplifyCfgOpts));
	_addInstrCombinePasses(FPM, false, false, false);

	FPM.addPass(hwtHls::StreamReadLoweringPass());
	_addInstrCombinePasses(FPM, false, false, false);
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass(true, false));
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(SimplifyCfgOpts));
	_addInstrCombinePasses(FPM, false, false, false, true);

	FPM.addPass(hwtHls::StreamWriteLoweringPass());
	_addInstrCombinePasses(FPM, false, false);
	FPM.addPass(hwtHls::TrivialSimplifyCFGPass(true, false));
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(SimplifyCfgOpts));
	_addInstrCombinePasses(FPM, false, false);
	//FPM.addPass(hwtHls::DumpAndExitPass(
	//	true, false, "tmp/HwtHlsSimplifyCFGPass.begin.dot"));
		
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());
	//FPM.addPass(hwtHls::DumpAndExitPass(
	//	true, false, "tmp/HwtHlsSimplifyCFGPass.end.dot"));
	FPM.addPass(llvm::LoopSimplifyPass());
	FPM.addPass(hwtHls::StreamSegmentLoopUnrollPass());
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());
}

void LlvmCompilationBundle::_addCommonPasses(llvm::FunctionPassManager &FPM) {
	// Delete small array after loop unroll.
	FPM.addPass(llvm::SROAPass(llvm::SROAOptions::ModifyCFG));
	// The matrix extension can introduce large vector operations early, which
	// can benefit from running vector-combine early on.
	//  if (EnableMatrix)
	//    FPM.addPass(VectorCombinePass(/*ScalarizationOnly=*/true));
	// Eliminate redundancies.
	FPM.addPass(llvm::MergedLoadStoreMotionPass(
		llvm::MergedLoadStoreMotionOptions(/*SplitFooterBB=*/
										   true)));
	// if (RunNewGVN)
	//  FPM.addPass(llvm::NewGVNPass());
	// else
	FPM.addPass(llvm::GVNPass());
	// Sparse conditional constant propagation.
	// FIXME: It isn't clear why we do this *after* loop passes rather than
	// before...
	FPM.addPass(llvm::SCCPPass());
	// Delete dead bit computations (instcombine runs after to fold away the
	// dead computations, and then ADCE will run later to exploit any new DCE
	// opportunities that creates).
	FPM.addPass(llvm::BDCEPass());

	// Run instcombine after redundancy and dead bit elimination to exploit
	// opportunities opened up by them.
	_addInstrCombinePassesLight(FPM);

	// invokePeepholeEPCallbacks(FPM, Level);
	//  Re-consider control flow based optimizations after redundancy
	//  elimination, redo DCE, etc.
	//   if (EnableDFAJumpThreading && Level.getSizeLevel() == 0)
	FPM.addPass(llvm::DFAJumpThreadingPass());
	FPM.addPass(llvm::JumpThreadingPass()); // segfault on insert to internal
											// set in non debug builds
	// :note: DFAJumpThreadingPass will left unreachable blocks with branch
	// condition set to undef, there we remove such blocks
	FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass());
	FPM.addPass(llvm::CorrelatedValuePropagationPass());
	// Finally, do an expensive DCE pass to catch all the dead code exposed by
	// the simplifications and basic cleanup after all the simplifications.
	// TODO: Investigate if this is too expensive.
	FPM.addPass(llvm::ADCEPass());
	// Specially optimize memory movement as it doesn't look like dataflow in
	// SSA.
	FPM.addPass(llvm::MemCpyOptPass());
	FPM.addPass(llvm::DSEPass());
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
		llvm::LICMPass(PTO.LicmMssaOptCap,
					   PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
					   true),
		/*UseMemorySSA=*/true,
		/*UseBlockFrequencyInfo=*/true));

	// FPM.addPass(llvm::CoroElidePass());
	//	for (auto &C : ScalarOptimizerLateEPCallbacks)
	//		C(FPM, Level);
	{
		auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions()  //
								   .convertSwitchRangeToICmp(true) //
								   .hoistCommonInsts(true)		   //
								   .sinkCommonInsts(true)		   //
			;
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}
	_addInstrCombinePassesLight(FPM);
}

void LlvmCompilationBundle::_addInstrCombinePassesLight(
	llvm::FunctionPassManager &FPM) {
	FPM.addPass(hwtHls::RomExtractPass());
	FPM.addPass(hwtHls::HwtHlsInstCombinePass());
	FPM.addPass(llvm::InstCombinePass());
	FPM.addPass(hwtHls::HwtHlsInstCombinePass());
}

void LlvmCompilationBundle::_addInstrCombinePasses(
	llvm::FunctionPassManager &FPM, bool bitwidthReduction, bool selectPruning,
	bool llvmInstrCombine, bool streamReadEoFThreading,
	bool hwtHlsFpInstrCombine) {
	// [todo]
	//  if (II.getCalledFunction()->isTargetIntrinsic()) {
	//    return TTI.instCombineIntrinsic(*this, II);
	//  }
	FPM.addPass(llvm::EarlyCSEPass());
	FPM.addPass(hwtHls::RomExtractPass());
	{
		auto icOpts = HwtHlsInstCombinePassOptions()						 //
						  .setStreamReadEoFThreading(streamReadEoFThreading) //
						  .setHwtHlsFpCombining(hwtHlsFpInstrCombine)		 //
			;
		FPM.addPass(hwtHls::HwtHlsInstCombinePass(icOpts));
	}
	if (llvmInstrCombine) {
		FPM.addPass(llvm::InstCombinePass()); // hwtHls specific
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
		FPM.addPass(llvm::AggressiveInstCombinePass()); // hwtHls specific
	}
	if (bitwidthReduction) {
		FPM.addPass(hwtHls::BitwidthReductionPass());
		FPM.addPass(llvm::InstCombinePass()); // hwtHls specific
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
	}
	if (selectPruning) {
		FPM.addPass(hwtHls::SelectPruningPass());
		FPM.addPass(hwtHls::HwtHlsInstCombinePass());
		FPM.addPass(llvm::InstCombinePass()); // hwtHls specific
	}
	if (llvmInstrCombine || bitwidthReduction || selectPruning) {
		auto icOpts = HwtHlsInstCombinePassOptions()				  //
						  .setHwtHlsFpCombining(hwtHlsFpInstrCombine) //
			;
		FPM.addPass(hwtHls::HwtHlsInstCombinePass(icOpts));
	}
}

void LlvmCompilationBundle::_addAfterUnrollFollowupPasses(
	llvm::FunctionPassManager &FPM) {
	llvm::LoopPassManager LPM;
	// We provide the opt remark emitter pass for LICM to use. We only need to
	// do this once as it is immutable.
	FPM.addPass(
		llvm::RequireAnalysisPass<llvm::OptimizationRemarkEmitterAnalysis,
								  llvm::Function>());

	// LoopSimplifyPass should be added automatically
	// https://llvm.org/docs/LoopTerminology.html#loop-simplify-form :note: This
	// LoopSimplifyPass is not added automatically
	LPM.addPass(hwtHls::LoopFlattenUsingIfPass());
	FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
		std::move(LPM), /*UseMemorySSA=*/
		false,
		/*UseBlockFrequencyInfo=*/true,
		/*UseBranchProbabilityInfo=*/true));
	{
		auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions() //
								   .hoistCommonInsts(true)		  //
								   .setHoistCheapInsts(true)	  //
			;
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}
	// FPM.addPass(hwtHls::DumpAndExitPass(false, false,
	// "tmp/debug.5.afterLoopFlattenUsingIfPass.dot", true));
}

void LlvmCompilationBundle::_addLoopPasses(llvm::FunctionPassManager &FPM) {
	// FPM.addPass(llvm::LoopSimplifyPass()); // added automatically by PM

	// Add the primary loop simplification pipeline.
	// FIXME: Currently this is split into two loop pass pipelines because we
	// run some function passes in between them. These can and should be removed
	// and/or replaced by scheduling the loop pass equivalents in the correct
	// positions. But those equivalent passes aren't powerful enough yet.
	// Specifically, `SimplifyCFGPass` and `InstCombinePass` are currently still
	// used. We have `LoopSimplifyCFGPass` which isn't yet powerful enough yet
	// to fully replace `SimplifyCFGPass`, and the closest to the other we have
	// is `LoopInstSimplify`.
	llvm::LoopPassManager LPM1, LPM2;
	// LPM1.addPass(hwtHls::LoopBackedgeSimplifyPass());
	//  Simplify the loop body. We do this initially to clean up after other
	//  loop passes run, either when iterating on a loop or on inner loops with
	//  implications on the outer loop.
	LPM1.addPass(llvm::LoopInstSimplifyPass());
	LPM1.addPass(llvm::LoopSimplifyCFGPass());
	// Try to remove as much code from the loop header as possible,
	// to reduce amount of IR that will have to be duplicated.
	// TODO: Investigate promotion cap for O1.
	LPM1.addPass(
		llvm::LICMPass(PTO.LicmMssaOptCap,
					   PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
					   false));
	// Disable header duplication in loop rotation at -Oz.
	LPM1.addPass(llvm::LoopRotatePass(false, /*PrepareForLTO*/
									  false));
	// TODO: Investigate promotion cap for O1.
	LPM1.addPass(
		llvm::LICMPass(PTO.LicmMssaOptCap,
					   PTO.LicmMssaNoAccForPromotionCap, /*AllowSpeculation=*/
					   true));
	LPM1.addPass(
		llvm::SimpleLoopUnswitchPass(/* NonTrivial */
									 Level == llvm::OptimizationLevel::O3 &&
									 EnableO3NonTrivialUnswitching));
	// if (EnableLoopFlatten)
	//   LPM1.addPass(llvm::LoopFlattenPass());
	// LPM1.addPass(hwtHls::LoopBackedgeSimplifyPass());
	LPM2.addPass(llvm::LoopIdiomRecognizePass());
	LPM2.addPass(llvm::IndVarSimplifyPass(/*WidenIndVars*/ true));
	// for (auto &C : LateLoopOptimizationsEPCallbacks)
	//   C(LPM2, Level);
	LPM2.addPass(llvm::LoopDeletionPass());
	// if (EnableLoopInterchange)
	// LPM2.addPass(llvm::LoopInterchangePass());
	//  Do not enable unrolling in PreLinkThinLTO phase during sample PGO
	//  because it changes IR to makes profile annotation in back compile
	//  inaccurate. The normal unroller doesn't pay attention to forced full
	//  unroll attributes so we need to make sure and allow the full unroll pass
	//  to pay attention to it.
	// if (Phase != ThinOrFullLTOPhase::ThinLTOPreLink || !PGOOpt ||
	//     PGOOpt->Action != PGOOptions::SampleUse)
	//   LPM2.addPass(LoopFullUnrollPass(Level.getSpeedupLevel(),
	//                                   /* OnlyWhenForced= */
	//                                   !PTO.LoopUnrolling,
	//                                   PTO.ForgetAllSCEVInLoopUnroll));
	// for (auto &C : LoopOptimizerEndEPCallbacks)
	//   C(LPM2, Level);
	//  We provide the opt remark emitter pass for LICM to use. We only need to
	//  do this once as it is immutable.
	FPM.addPass(
		llvm::RequireAnalysisPass<llvm::OptimizationRemarkEmitterAnalysis,
								  llvm::Function>());
	FPM.addPass(
		llvm::createFunctionToLoopPassAdaptor(std::move(LPM1), /*UseMemorySSA=*/
											  true, /*UseBlockFrequencyInfo=*/
											  true));
	{
		auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions()  //
								   .convertSwitchRangeToICmp(true) //
			;
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}

	FPM.addPass(llvm::LoopSimplifyPass());
	_addInstrCombinePassesLight(FPM);

	// The loop passes in LPM2 (LoopIdiomRecognizePass, IndVarSimplifyPass,
	// LoopDeletionPass and LoopFullUnrollPass) do not preserve MemorySSA.
	// *All* loop passes must preserve it, in order to be able to use it.
	FPM.addPass(
		createFunctionToLoopPassAdaptor(std::move(LPM2), /*UseMemorySSA=*/
										false, /*UseBlockFrequencyInfo=*/
										false));
}

// :note: based on  llvm::PassBuilder::addVectorPasses
void LlvmCompilationBundle::_addVectorPasses(llvm::OptimizationLevel Level,
											 llvm::FunctionPassManager &FPM,
											 bool IsFullLTO) {
	// based on PassBuilder::addVectorPasses

	// important for LoopUnrollPass because otherwise it generates obscure
	// prolog for loops with dynamic range
	FPM.addPass(hwtHls::LoopAddLatchPass());
	FPM.addPass(llvm::LoopSimplifyPass());

	FPM.addPass(llvm::LoopVectorizePass(llvm::LoopVectorizeOptions(
		!PTO.LoopInterleaving, !PTO.LoopVectorization)));
	if (IsFullLTO) {
		HwtFpgaAllowVolatileMemOpDuplication _(TM, FPM);
		// The vectorizer may have significantly shortened a loop body; unroll
		// again. Unroll small loops to hide loop backedge latency and saturate
		// any parallel execution resources of an out-of-order processor. We
		// also then need to clean up redundancies and loop invariant code.
		// FIXME: It would be really good to use a loop-integrated instruction
		// combiner for cleanup here so that the unrolling and LICM can be
		// pipelined across the loop nests. We do UnrollAndJam in a separate LPM
		// to ensure it happens before unroll
		if (PTO.LoopUnrolling)
			FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
				llvm::LoopUnrollAndJamPass(Level.getSpeedupLevel())));
		FPM.addPass(llvm::LoopUnrollPass(
			llvm::LoopUnrollOptions(Level.getSpeedupLevel(), /*OnlyWhenForced=*/
									!PTO.LoopUnrolling,
									PTO.ForgetAllSCEVInLoopUnroll) //
				.setPartial(false)								   //
				.setPeeling(false)								   //
				.setRuntime(false)								   //
				.setProfileBasedPeeling(false)));
		_addAfterUnrollFollowupPasses(FPM);
		FPM.addPass(llvm::WarnMissedTransformationsPass());
	}

	if (!IsFullLTO) {
		// Eliminate loads by forwarding stores from the previous iteration to
		// loads of the current iteration.
		FPM.addPass(llvm::LoopLoadEliminationPass());
		// :note: LoopFusePass works only with loops with exactly same iteration
		// scheme, for hw this may not be sufficient
		FPM.addPass(llvm::LoopFusePass());
		FPM.addPass(llvm::LoopDistributePass());
	}
	// Cleanup after the loop optimization passes.
	_addInstrCombinePassesLight(FPM);

	if (Level.getSpeedupLevel() > 1) { //  && ExtraVectorizerPasses
		llvm::ExtraFunctionPassManager<llvm::ShouldRunExtraVectorPasses>
			ExtraPasses;
		// At higher optimization levels, try to clean up any runtime overlap
		// and alignment checks inserted by the vectorizer. We want to track
		// correlated runtime checks for two inner loops in the same outer loop,
		// fold any common computations, hoist loop-invariant aspects out of any
		// outer loop, and unswitch the runtime checks if possible. Once
		// hoisted, we may have dead (or speculatable) control flows or more
		// combining opportunities.
		ExtraPasses.addPass(llvm::EarlyCSEPass());
		ExtraPasses.addPass(llvm::CorrelatedValuePropagationPass());
		_addInstrCombinePassesLight(FPM);

		llvm::LoopPassManager LPM;
		LPM.addPass(llvm::LICMPass(PTO.LicmMssaOptCap,
								   PTO.LicmMssaNoAccForPromotionCap,
								   /*AllowSpeculation=*/true));
		LPM.addPass(llvm::SimpleLoopUnswitchPass(
			/* NonTrivial */ Level == llvm::OptimizationLevel::O3));
		ExtraPasses.addPass(
			llvm::RequireAnalysisPass<llvm::OptimizationRemarkEmitterAnalysis,
									  llvm::Function>());
		ExtraPasses.addPass(
			createFunctionToLoopPassAdaptor(std::move(LPM), /*UseMemorySSA=*/
											true,
											/*UseBlockFrequencyInfo=*/true));
		{
			auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions()  //
									   .convertSwitchRangeToICmp(true) //
				;
			ExtraPasses.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
		}
		ExtraPasses.addPass(llvm::LoopSimplifyPass());
		ExtraPasses.addPass(hwtHls::RomExtractPass());
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
	{
		auto simplifyCfgOpts = hwtHls::HwtHlsSimplifyCFGOptions()  //
								   .forwardSwitchCondToPhi(true)   //
								   .convertSwitchRangeToICmp(true) //
								   //.convertSwitchToLookupTable(true)//
								   .needCanonicalLoops(true) //
								   .hoistCommonInsts(true)	 //
								   .sinkCommonInsts(true);
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass(simplifyCfgOpts));
	}

	FPM.addPass(llvm::LoopSimplifyPass());

	if (IsFullLTO) {
		FPM.addPass(llvm::SCCPPass());
		FPM.addPass(hwtHls::RomExtractPass());
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
		FPM.addPass(hwtHls::RomExtractPass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(hwtHls::LoopAddLatchPass());
		FPM.addPass(llvm::LoopSimplifyPass());
		{
			HwtFpgaAllowVolatileMemOpDuplication _(TM, FPM);
			// Unroll small loops to hide loop backedge latency and saturate any
			// parallel execution resources of an out-of-order processor. We
			// also then need to clean up redundancies and loop invariant code.
			// FIXME: It would be really good to use a loop-integrated
			// instruction combiner for cleanup here so that the unrolling and
			// LICM can be pipelined across the loop nests. We do UnrollAndJam
			// in a separate LPM to ensure it happens before unroll
			if (PTO.LoopUnrolling) { // EnableUnrollAndJam &&
				FPM.addPass(llvm::createFunctionToLoopPassAdaptor(
					llvm::LoopUnrollAndJamPass(Level.getSpeedupLevel())));
			}

			// FPM.addPass(hwtHls::DumpAndExitPass(false, false,
			// "tmp/_addAfterUnrollFollowupPasses.0-before.dot", true, true));
			{
				auto luOpts =
					llvm::LoopUnrollOptions(
						Level.getSpeedupLevel(), /*OnlyWhenForced=*/
						!PTO.LoopUnrolling, PTO.ForgetAllSCEVInLoopUnroll) //
						.setPartial(false)								   //
						.setPeeling(false)								   //
						.setRuntime(false)								   //
						.setProfileBasedPeeling(false)					   //
					;
				FPM.addPass(llvm::LoopUnrollPass(luOpts));
			}
			_addAfterUnrollFollowupPasses(FPM);
			FPM.addPass(llvm::WarnMissedTransformationsPass());
		}
		FPM.addPass(hwtHls::RomExtractPass());
		FPM.addPass(llvm::InstCombinePass());
		FPM.addPass(
			llvm::RequireAnalysisPass<llvm::OptimizationRemarkEmitterAnalysis,
									  llvm::Function>());
		FPM.addPass(createFunctionToLoopPassAdaptor(
			llvm::LICMPass(PTO.LicmMssaOptCap, PTO.LicmMssaNoAccForPromotionCap,
						   /*AllowSpeculation=*/true),
			/*UseMemorySSA=*/true, /*UseBlockFrequencyInfo=*/true));
		FPM.addPass(hwtHls::HwtHlsSimplifyCFGPass()); // hwtHls specific
		FPM.addPass(llvm::LoopSimplifyPass());
	}

	// Now that we've vectorized and unrolled loops, we may have more refined
	// alignment information, try to re-derive it here.
	FPM.addPass(llvm::AlignmentFromAssumptionsPass());

	if (IsFullLTO) {
		_addInstrCombinePassesLight(FPM);
	}
}

void LlvmCompilationBundle::_addMachineCodegenPasses(
	hwtHls::HwtFpgaToNetlist::ConvesionFnT &toNetlistConversionFn) {

	// llvm::MachineFunctionAnalysisManager MFAM;
	// llvm::MachineFunctionPassManager MPM;
	//
	// if (auto e = MPM.run(*fn.getParent(), MFAM)) {
	//	throw std::runtime_error("Error during running
	//MachineFunctionPassManager");
	// }

	// use CodeGenPassBuilder once complete

	// :info: based on llc.cpp
	PM.add(MMIWP);

	// check for incompatible passes
	TPC = static_cast<llvm::HwtFpgaTargetPassConfig *>(
		static_cast<llvm::TargetMachine &>(*TM).createPassConfig(PM));
	// :note: we can not use pass constructor to pass toNetlistConversionFn
	//    because constructor must be callable without arguments because of
	//    INITIALIZE_PASS macros
	// :note: we can not call pass explicitly after PM.run() because
	// addRequired/getAnalysis will not work
	TPC->toNetlistConversionFn = &toNetlistConversionFn;
	if (TPC->hasLimitedCodeGenPipeline()) {
		llvm::errs() << "run-pass cannot be used with "
					 << TPC->getLimitedCodeGenPipelineReason() << ".\n";
		throw std::runtime_error("run-pass cannot be used with ...");
	}
	// PM.add(llvm::createCFGPrinterLegacyPassPass());
	// //llvm::CFGPrinterPass());

	PM.add(TPC);

	// add passes which convert llvm::Function to llvm::MachineFunction
	if (TPC->addISelPasses())
		llvm_unreachable("Can not addISelPasses");
	TPC->printAndVerify("before addMachinePasses");
	TPC->addMachinePasses(); // add main bundle of Machine level optimizations
	// place for custom machine passes
	TPC->printAndVerify("after addMachinePasses");
	TPC->setInitialized();

	PM.add(llvm::createFreeMachineFunctionPass());
}

}
