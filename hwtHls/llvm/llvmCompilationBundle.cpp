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
#include <llvm/ADT/Statistic.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/PassTimingInfo.h>
#include <llvm/Pass.h>
#include <llvm/Passes/StandardInstrumentations.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Target/TargetMachine.h>
//#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/CodeGen.h>
#include <llvm/CodeGen/Passes.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/Analysis/TargetLibraryInfo.h>

#include <hwtHls/llvm/llvmCompilationBundleORE.h>
#include <hwtHls/llvm/llvmHwtHlsInstrumentation.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

namespace hwtHls {

const std::string LlvmCompilationBundle::TargetTriple =
		"hwtFpga-unknown-linux-gnu";
const std::string LlvmCompilationBundle::CPU = "model0";
const std::string LlvmCompilationBundle::Features = "model0";

// :note: copied from llvm-opt
using DebugLogging = LlvmCompilationBundle::DebugLogging;
static llvm::cl::opt<DebugLogging> DebugPMCliOpt("debug-pass-manager",
		llvm::cl::Hidden, llvm::cl::ValueOptional,
		llvm::cl::desc("Print pass management debugging information"),
		llvm::cl::init(DebugLogging::None),
		llvm::cl::values(clEnumValN(DebugLogging::Normal, "", ""),
				clEnumValN(DebugLogging::Quiet, "quiet",
						"Skip printing info about analyses"),
				clEnumValN(DebugLogging::Verbose, "verbose",
						"Print extra information about adaptors and pass managers")));
static llvm::cl::opt<bool> VerifyEach("verify-each",
		llvm::cl::desc("Verify after each transform"));

// https://discourse.llvm.org/t/how-to-implement-a-disable-pass-option/71149/12
LlvmCompilationBundle::LlvmCompilationBundle(const std::string &moduleName,
		const std::vector<LlvmCliOptionTuple> &llvmCliOpts) :
		ctx(), strCtx(), module(
				new llvm::Module(strCtx.addStringRef(moduleName), ctx)), builder(
				ctx), main(nullptr), MMIWP(nullptr), VerifyEachPass(VerifyEach), DebugPM(
				DebugPMCliOpt.getValue()), llvmCliOpts(
				llvmCliOpts) {
	// clear all current CLI options
	_llvmCliOpts_clear();
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
	TM->setOptLevel(llvm::CodeGenOptLevel::Aggressive);
	PTO = llvm::PipelineTuningOptions();
	llvm::LLVMTargetMachine &LLVMTM = static_cast<llvm::LLVMTargetMachine&>(*TM);
	MMIWP = new llvm::MachineModuleInfoWrapperPass(&LLVMTM);
	_registerHwtHlsPasses();
	_updateDebugPM();
	module->setDataLayout(TM->createDataLayout());
}


void LlvmCompilationBundle::_updateDebugPM() {
	DebugPM = DebugPMCliOpt.getValue();
	PrintPassOpts.Verbose = DebugPM == DebugLogging::Verbose;
	PrintPassOpts.SkipAnalyses = DebugPM == DebugLogging::Quiet;
}

void LlvmCompilationBundle::_initPassBuilder() {
	assert(
			PB.get() == nullptr
					&& "LlvmCompilationBundle::_initPassBuilder() should be called only once after all options are set");
	// this assert is required in order to prevent unintentional delete of previous PB and specially AMs while compilation is still running
	_llvmCliOpts_apply();
	RemarksFile = LlvmCompilationBundle_registerORE(ctx);
	if (RemarksFile)
		RemarksFile->keep();
	// :note: this is not done in constructor because options set from python are require to be initialized
	LAM = std::make_unique<llvm::LoopAnalysisManager>();
	CGAM = std::make_unique<llvm::CGSCCAnalysisManager>();
	MAM = std::make_unique<llvm::ModuleAnalysisManager>();
	FAM = std::make_unique<llvm::FunctionAnalysisManager>();

	// pre-populate TLI to customize set of library functions
	// :note: this can not be moved behind PB->crossRegisterProxies()
	llvm::TargetLibraryInfoImpl TLII(llvm::Triple(TM->getTargetTriple()));
	TLII.setAvailable(llvm::LibFunc::LibFunc_sinpi);
	TLII.setAvailable(llvm::LibFunc::LibFunc_cospi);
	TLII.setAvailable(llvm::LibFunc::LibFunc_sincospi_stret);
	FAM->registerPass([&] { return llvm::TargetLibraryAnalysis(TLII); });

	// PIC same as in llvm/toools/opt/NewPMDriver.cpp llvm::runPassPipeline()
	SI = std::make_unique<llvm::StandardInstrumentations>(ctx,
			DebugPM != DebugLogging::None, VerifyEachPass, PrintPassOpts);
	SI->registerCallbacks(PIC, &*MAM);
	hwtHls::registerInstrumenationHwtHlsSkipPass(PIC);

	PB = std::make_unique<llvm::PassBuilder>(
	/*TargetMachine *TM = */TM,
	/* PipelineTuningOptions PTO = */PTO,
	/*Optional<PGOOptions> PGOOpt =*/std::nullopt,
	/*PassInstrumentationCallbacks *PIC =*/&PIC);

	PB->registerModuleAnalyses(*MAM);
	PB->registerCGSCCAnalyses(*CGAM);
	PB->registerFunctionAnalyses(*FAM);
	PB->registerLoopAnalyses(*LAM);
	PB->crossRegisterProxies(*LAM, *FAM, *CGAM, *MAM);
	{
		auto  &TLI = FAM->getResult<llvm::TargetLibraryAnalysis>(*main);
		assert(TLI.has(llvm::LibFunc::LibFunc_sinpi) && "Sanity check that the custom TargetLibraryAnalysis was registered correctly");
	}
}


llvm::TargetLibraryInfo& LlvmCompilationBundle::getTargetLibraryInfo() {
	if (!main) {
		throw std::runtime_error(
				"getTargetLibraryInfo requires main function to be specified");
	}
	if (!PB) {
		_initPassBuilder();
	}
	auto  &res = FAM->getResult<llvm::TargetLibraryAnalysis>(*main);
	assert(res.has(llvm::LibFunc::LibFunc_sinpi));
	return res;
}

void LlvmCompilationBundle::_llvmCliOpts_apply() {
	_llvmCliOpts_clear();
	for (const auto& opt: llvmCliOpts) {
		_llvmCliOption_add(std::get<0>(opt), std::get<1>(opt), std::get<2>(opt), std::get<3>(opt));
	}
}

void LlvmCompilationBundle::_llvmCliOpts_clear() {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	for (auto &Opt : Map) {
		Opt.second->reset();
	}
}

void LlvmCompilationBundle::_llvmCliOption_add(
		const std::string &OptionName, unsigned pos, const std::string &ArgName,
		const std::string &ArgValue) {
	llvm::StringMap<llvm::cl::Option*> &Map = llvm::cl::getRegisteredOptions();
	auto o = Map.find(OptionName);
	if (o == Map.end()) {
		if (OptionName == "debug-only") {
			throw std::runtime_error(
					"debug-only LLVM cli option is available only in LLVM debug build");
		} else {
			throw std::runtime_error(
					std::string("Can not find LLVM cli option ") + OptionName);
		}
	}
	o->second->addOccurrence(pos, strCtx.addStringRef(ArgName),
			strCtx.addStringRef(ArgValue));
	if (OptionName == "debug-pass-manager") {
		_updateDebugPM();
	} else if (OptionName == "verify-each") {
		VerifyEachPass = VerifyEach;
	}
}

llvm::MachineFunction* LlvmCompilationBundle::getMachineFunction(
		llvm::Function &fn) {
	auto &MMI = MMIWP->getMMI();
	return MMI.getMachineFunction(fn);
}

llvm::MachineModuleInfo* LlvmCompilationBundle::getMachineModuleInfo() {
	return &MMIWP->getMMI();
}

LlvmCompilationBundle::~LlvmCompilationBundle() {
	if (TM) {
		delete TM; // MMIWP deleted as a part of TM
	} else if (MMIWP) {
		delete MMIWP;
	}
}

}
