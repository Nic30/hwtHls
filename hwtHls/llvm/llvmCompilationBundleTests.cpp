#include <hwtHls/llvm/llvmCompilationBundle.h>

#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/MIRPrinter.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/CodeGen/MIRParser/MIRParser.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/IR/Function.h>
#include <llvm/MC/MCInstrInfo.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Target/TargetMachine.h>

#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>
#include <hwtHls/llvm/Transforms/LoopUnrotatePass.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>
#include <hwtHls/llvm/Transforms/utils/bitSliceFlattening.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreLegalizerCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreRegAllocCombiner.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreToNetlistCombiner.h>
#include <hwtHls/llvm/targets/hwtFpgaMCTargetDesc.h>
#include <hwtHls/llvm/targets/Transforms/EarlyMachineCopyPropagation.h>
#include <hwtHls/llvm/targets/Transforms/vregIfConversion.h>
#include <hwtHls/llvm/llvmIrCommon.h>

using namespace llvm;

namespace hwtHls {

llvm::Function& LlvmCompilationBundle::_runCustomFunctionPass(
		std::function<void(llvm::FunctionPassManager&)> addPasses) {
	if (!main)
		throw std::runtime_error("Main function not specified");
	auto &fn = *main;
	fn.getParent()->setDataLayout(TM->createDataLayout());

	auto LAM = llvm::LoopAnalysisManager { };
	auto cgscc_manager = llvm::CGSCCAnalysisManager { };
	auto MAM = llvm::ModuleAnalysisManager { };
	auto FAM = llvm::FunctionAnalysisManager { };
	// PIC same as in llvm/toools/opt/NewPMDriver.cpp llvm::runPassPipeline()
	llvm::StandardInstrumentations SI(ctx, DebugPM != DebugLogging::None,
			VerifyEachPass, PrintPassOpts);
	SI.registerCallbacks(PIC, &FAM);
	_initPassBuilder();
	PB->registerModuleAnalyses(MAM);
	PB->registerCGSCCAnalyses(cgscc_manager);
	PB->registerFunctionAnalyses(FAM);
	PB->registerLoopAnalyses(LAM);
	PB->crossRegisterProxies(LAM, FAM, cgscc_manager, MAM);

	llvm::FunctionPassManager FPM;
	addPasses(FPM);
	FPM.run(fn, FAM);
	return fn;
}

void LlvmCompilationBundle::_testMachineFunctionPass(
		std::function<void(llvm::HwtFpgaTargetPassConfig&)> addPasses) {
	if (!main)
		throw std::runtime_error("Main function not specified");
	auto &fn = *main;
	fn.getParent()->setDataLayout(TM->createDataLayout());

	auto LAM = llvm::LoopAnalysisManager { };
	auto cgscc_manager = llvm::CGSCCAnalysisManager { };
	auto MAM = llvm::ModuleAnalysisManager { };
	auto FAM = llvm::FunctionAnalysisManager { };
	// PIC same as in llvm/toools/opt/NewPMDriver.cpp llvm::runPassPipeline()
	llvm::StandardInstrumentations SI(ctx, DebugPM != DebugLogging::None,
			VerifyEachPass, PrintPassOpts);
	SI.registerCallbacks(PIC, &FAM);
	_initPassBuilder();
	PB->registerModuleAnalyses(MAM);
	PB->registerCGSCCAnalyses(cgscc_manager);
	PB->registerFunctionAnalyses(FAM);
	PB->registerLoopAnalyses(LAM);
	PB->crossRegisterProxies(LAM, FAM, cgscc_manager, MAM);

	PM.add(MMIWP);

	TPC =
			static_cast<llvm::HwtFpgaTargetPassConfig*>(static_cast<llvm::LLVMTargetMachine&>(*TM).createPassConfig(
					PM));
	if (TPC->hasLimitedCodeGenPipeline()) {
		llvm::errs() << "run-pass cannot be used with "
				<< TPC->getLimitedCodeGenPipelineReason(" and ") << ".\n";
		throw std::runtime_error("run-pass cannot be used with ...");
	}

	PM.add(TPC);
	TPC->printAndVerify("before addMachinePasses");

	addPasses(*TPC);

	TPC->printAndVerify("after addMachinePasses");
	TPC->setInitialized();
	PM.run(*module);
}

/////////////////////////////////////////////////////////////// IR tests ///////////////////////////////////////////////////////////////

llvm::Function& LlvmCompilationBundle::_testSimplifyCFG2Pass(
		int BonusInstThreshold,           //
		bool ForwardSwitchCondToPhi,      //
		bool ConvertSwitchRangeToICmp,    //
		bool ConvertSwitchToLookupTable,  //
		bool NeedCanonicalLoop,           //
		bool HoistCommonInsts,            //
		bool SinkCommonInsts,             //
		bool SimplifyCondBranch,          //
		bool FoldTwoEntryPHINode,         //
		bool HoistCheapInsts              //
		) {
	return _runCustomFunctionPass([
								   BonusInstThreshold,           //
								    ForwardSwitchCondToPhi,      //
								    ConvertSwitchRangeToICmp,    //
								    ConvertSwitchToLookupTable,  //
								    NeedCanonicalLoop,           //
								    HoistCommonInsts,            //
								    SinkCommonInsts,             //
								    SimplifyCondBranch,          //
								    FoldTwoEntryPHINode,         //
								    HoistCheapInsts              //
								   ](llvm::FunctionPassManager &FPM) {
		FPM.addPass(hwtHls::SimplifyCFG2Pass(hwtHls::SimplifyCFG2Options()//
				.bonusInstThreshold(BonusInstThreshold)//
				.forwardSwitchCondToPhi(ForwardSwitchCondToPhi)//
				.convertSwitchRangeToICmp(ConvertSwitchRangeToICmp)//
				.convertSwitchToLookupTable(ConvertSwitchToLookupTable)//
				.needCanonicalLoops(NeedCanonicalLoop)//
				.hoistCommonInsts(HoistCommonInsts)//
				.sinkCommonInsts(SinkCommonInsts)//
				.setSimplifyCondBranch(SimplifyCondBranch)//
				.setFoldTwoEntryPHINode(FoldTwoEntryPHINode)//
				.setHoistCheapInsts(HoistCheapInsts)
		));
	});
}
llvm::Function& LlvmCompilationBundle::_testBitwidthReductionPass() {
	return _runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		FPM.addPass(hwtHls::BitwidthReductionPass());
	});
}

llvm::Function& LlvmCompilationBundle::_testSlicesMergePass() {
	return _runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		FPM.addPass(hwtHls::SlicesMergePass());
	});
}

llvm::Function& LlvmCompilationBundle::_testLoopUnrotatePass() {
	return _runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		llvm::LoopPassManager LPM0;
		LPM0.addPass(hwtHls::LoopUnrotatePass());

		FPM.addPass(llvm::createFunctionToLoopPassAdaptor(std::move(LPM0),
				/*UseMemorySSA=*/ false,
				/*UseBlockFrequencyInfo=*/ false));
	});
}

llvm::Function& LlvmCompilationBundle::_testSlicesToIndependentVariablesPass() {
	return _runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		FPM.addPass(hwtHls::SlicesToIndependentVariablesPass());
		FPM.addPass(llvm::ADCEPass());
	});
}

// rewriteExtractOnMergeValues function wrapped in pass class for testing purposes
class RewriteExtractOnMergeValuesPass: public llvm::PassInfoMixin<
		SlicesToIndependentVariablesPass> {
public:
	explicit RewriteExtractOnMergeValuesPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		TargetLibraryInfo *TLI = &AM.getResult<TargetLibraryAnalysis>(F);
		bool Changed = false;
		DceWorklist dce(TLI, nullptr);
		IRBuilder<> Builder(&*F.begin()->begin());
		for (BasicBlock &BB : F) {
			for (auto I = BB.begin(); I != BB.end();) {
				if (llvm::CallInst *CI = dyn_cast<llvm::CallInst>(&*I)) {
					if (IsBitRangeGet(CI)) {
						if (rewriteExtractOnMergeValues(Builder, CI) != CI
								&& dce.tryRemoveIfDead(*I, I)) {
							dce.runToCompletition(I);
							Changed = true;
							continue;
						}
					}
				}
				++I;
			}
		}
		if (!Changed) {
			return llvm::PreservedAnalyses::all();
		}
		llvm::PreservedAnalyses PA;
		PA.preserveSet<llvm::CFGAnalyses>();
		return PA;
	}
};

llvm::Function& LlvmCompilationBundle::_testRewriteExtractOnMergeValues() {
	return _runCustomFunctionPass([](llvm::FunctionPassManager &FPM) {
		FPM.addPass(hwtHls::SlicesToIndependentVariablesPass());
	});
}

/////////////////////////////////////////////////////////////// MIR tests ///////////////////////////////////////////////////////////////
void LlvmCompilationBundle::_testEarlyIfConverter() {
	_testMachineFunctionPass([](llvm::HwtFpgaTargetPassConfig &TPC) {
		TPC._testAddPass(&llvm::EarlyIfPredicatorID);
		TPC._testAddPass(&llvm::EarlyIfConverterID);
	});
}

void LlvmCompilationBundle::_testVRegIfConverter() {
	_testMachineFunctionPass([](llvm::HwtFpgaTargetPassConfig &TPC) {
		TPC._testAddPass(hwtHls::createVRegIfConverter(nullptr));
	});
}

void LlvmCompilationBundle::_testVRegIfConverterForIr(bool lowerSsaToNonSsa) {
	_testMachineFunctionPass([lowerSsaToNonSsa](llvm::HwtFpgaTargetPassConfig &TPC) {
		if (TPC.addISelPasses())
			llvm_unreachable("Can not addISelPasses");
		if (lowerSsaToNonSsa) {
			TPC._testAddPass(&llvm::PHIEliminationID);
		}
		TPC._testAddPass(hwtHls::createVRegIfConverter(nullptr));
		//TPC._testAddPass(llvm::createHwtFpgaPreRegAllocCombiner());
		//TPC._testAddPass(&hwtHls::EarlyMachineCopyPropagationID);
		//TPC._testAddPass(&llvm::MachineCombinerID);

	});
}

}
