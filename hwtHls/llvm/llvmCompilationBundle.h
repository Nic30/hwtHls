#pragma once
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/Passes/StandardInstrumentations.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/MC/TargetRegistry.h>
#include <llvm/Support/ToolOutputFile.h>

#include <hwtHls/llvm/llvmIrStrings.h>
#include <hwtHls/llvm/targets/Transforms/hwtFpgaToNetlist.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>
#include <hwtHls/llvm/LegacyPassManagerWithPI.h>

namespace hwtHls {

/*
 * A container of all object which are required to compile the code with LLVM.
 * */
class LlvmCompilationBundle {
public:
	std::unique_ptr<llvm::LoopAnalysisManager> LAM;
	std::unique_ptr<llvm::CGSCCAnalysisManager> CGAM;
	std::unique_ptr<llvm::ModuleAnalysisManager> MAM;
	std::unique_ptr<llvm::FunctionAnalysisManager> FAM;
	std::unique_ptr<llvm::StandardInstrumentations> SI;
	std::unique_ptr<llvm::ToolOutputFile> RemarksFile;
	llvm::LLVMContext ctx;
	LLVMStringContext strCtx;
	llvm::Module *module;
	llvm::IRBuilder<> builder;
	llvm::Function *main;
	llvm::PassInstrumentationCallbacks PIC;
	llvm::PassInstrumentationCallbacks PICForLegacyPM;
	std::unique_ptr<llvm::PassBuilder> PB; // for IR passes
	LegacyPassManagerWithPI PM; // for machine code generator
	const llvm::Target *Target;
	llvm::HwtFpgaTargetPassConfig *TPC;
	llvm::OptimizationLevel Level;
	bool EnableO3NonTrivialUnswitching;
	bool EnableGVNHoist;
	bool EnableGVNSink;
	llvm::TargetMachine *TM;
	llvm::PipelineTuningOptions PTO;
	llvm::MachineModuleInfoWrapperPass *MMIWP;
	bool VerifyEachPass;
	enum class DebugLogging {
		None, Normal, Verbose, Quiet
	};
	DebugLogging DebugPM;
	llvm::PrintPassOptions PrintPassOpts;
	static const std::string TargetTriple;
	static const std::string CPU;
	static const std::string Features;

	// std::optional<std::function<void(std::function &)>> _dbgOnChangeCallbackForBitcountMergePass;
	// OptionName, position, ArgName, ArgValue
	using LlvmCliOptionTuple = std::tuple<std::string, unsigned, std::string, std::string>;

	// llvm cli options are stored there because they are global to whole program and when this object is currently
	// using llvm it must set its own llvm cli options first
	std::vector<LlvmCliOptionTuple> llvmCliOpts;
	llvm::StringMap<llvm::cl::Option*> &_llvmCliOpts; // reference to LLVM internal CLI opts

	LlvmCompilationBundle(const std::string &moduleName,
			const std::vector<LlvmCliOptionTuple> &llvmCliOpts);

	// ellipsis (...) operator used to iterate over all template arguments using recursion
	// template parameter list must end with void which is used as handle
	template<typename FirstPassCls, typename ... OtherPassClases,
	// enable only if FirstPassCls is void
			std::enable_if_t<std::is_void<FirstPassCls>::value, bool> = true>
	inline void __registerHwtHlsPasses() {
		// void is dummy type used as handle
	}
	template<typename FirstPassCls, typename ... OtherPassClases,
	// enable only if FirstPassCls is a class type
			std::enable_if_t<std::is_class<FirstPassCls>::value, bool> = true>
	inline void __registerHwtHlsPasses() {
		PIC.addClassToPassName(FirstPassCls::name(), FirstPassCls::name());
		PICForLegacyPM.addClassToPassName(FirstPassCls::name(),
				FirstPassCls::name());
		__registerHwtHlsPasses<OtherPassClases...>(); // process rest of template arguments
	}

	void _registerHwtHlsPasses();
	void _initPassBuilder();
	llvm::TargetLibraryInfo& getTargetLibraryInfo();
	// clear global llvm cli options and apply llvm cli options from this object
	void _llvmCliOpts_apply();
	// clear global llvm cli options
	void _llvmCliOpts_clear();
	// set a single global llvm cli option
	void _llvmCliOption_add(const std::string &OptionName, unsigned pos,
			const std::string &ArgName, const std::string &ArgValue);
	void _updateDebugPM();
	// for arg description see HwtFpgaTargetPassConfig
	// :param combinerCallback: is an optional callback function called during last state of
	//        instruction combining
	void runOpt(hwtHls::HwtFpgaToNetlist::ConvesionFnT toNetlistConversionFn,
			std::function<void(llvm::ModulePassManager&)> addExtraModulePasses);
	void _tryToFindMain();
	llvm::MachineFunction* getMachineFunction(llvm::Function &fn);

	llvm::MachineModuleInfo* getMachineModuleInfo();

	void _addInitialNormalizationPasses(llvm::FunctionPassManager &FPM);
	void _addStreamOperationLoweringPasses(llvm::FunctionPassManager &FPM);
	void _addLoopPasses(llvm::FunctionPassManager &FPM);
	void _addVectorPasses(llvm::OptimizationLevel Level,
			llvm::FunctionPassManager &FPM, bool IsFullLTO);

	// light version of _addInstrCombinePasses
	void _addInstrCombinePassesLight(llvm::FunctionPassManager &FPM);
	void _addInstrCombinePasses(llvm::FunctionPassManager &FPM,
			bool bitwidthReduction = true, bool selectPruning = true,
			bool llvmInstrCombine = true, bool streamReadEoFThreading = false,
			bool hwtHlsFpInstrCombine = false);
	void _addAfterUnrollFollowupPasses(llvm::FunctionPassManager &FPM);

	// for arg description see HwtFpgaTargetPassConfig
	void _addMachineCodegenPasses(
			hwtHls::HwtFpgaToNetlist::ConvesionFnT &toNetlistConversionFn);
	void _addCommonPasses(llvm::FunctionPassManager &FPM);

	void runExprOpt();

	// for param doc :see: HwtHlsSimplifyCFGOptions
	llvm::Function& _testHwtHlsSimplifyCFGPass(int BonusInstThreshold,        //
			bool ForwardSwitchCondToPhi,      //
			bool ConvertSwitchRangeToICmp,    //
			bool ConvertSwitchToLookupTable,  //
			bool NeedCanonicalLoop,           //
			bool HoistCommonInsts,            //
			bool SinkCommonInsts,             //
			bool SimplifyCondBranch,          //
			bool HoistCheapInsts              //
			);
	llvm::Function& _testLoopFlattenUsingIfPass();
	llvm::Function& _testRewriteExtractOnMergeValues();

	llvm::Module& _runCustomModulePass(
			std::function<void(llvm::ModulePassManager&)> addPasses);
	llvm::Function& _runCustomFunctionPass(
			std::function<void(llvm::FunctionPassManager&)> addPasses);
	llvm::Function& _runCustomLoopPass(
			std::function<void(llvm::LoopPassManager&)> addPasses);

	void _testMachineFunctionPass(
			std::function<void(llvm::HwtFpgaTargetPassConfig&)> addPasses);

	void _testEarlyIfConverter();
	void _testVRegIfConverter();
	// _testVRegIfConverter which has input in LLVM IR
	// (which is then translated to MIR which is then processed by VRegIfConverter)
	void _testVRegIfConverterForIr(bool lowerSsaToNonSsa);
	void _testHwtFpgaPreRegAllocGICombiner();
	void _testHwtFpgaPreToNetlistCombiner();
	~LlvmCompilationBundle();
};

}
