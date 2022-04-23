#include "genericFpgaTargetMachine.h"

#include <llvm/CodeGen/Passes.h>
//#include <llvm/CodeGen/SelectionDAGISel.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/FormattedStream.h>
#include <llvm/Support/TargetRegistry.h>
#include <llvm/Target/TargetOptions.h>
#include <llvm/MC/MCAsmInfo.h>

#include "genericFpga.h"
#include "genericFpgaTargetTransformInfo.h"
#include "genericFpgaTargetPassConfig.h"
#include "genericFpgaTargetInfo.h"
#include "genericFpgaTargetSubtarget.h"

extern "C" void LLVMInitializeGenericFpgaTarget() {
	// Register the target.
	llvm::RegisterTargetMachine<llvm::GenericFpgaTargetMachine> tmp(
			getTheGenericFpgaTarget());

	// Initialize target specific passes
	llvm::PassRegistry &PR = *llvm::PassRegistry::getPassRegistry();
	(void) PR;
}
namespace llvm {

static std::string computeDataLayout(const Triple &TT) {
	// 64b address up to 4096b regs, based on spir
	return "e-m:e-"
			"i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-"
			"n8:16:32:64-S128-"
			"v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024";
}

static Reloc::Model getEffectiveRelocModel(const Triple &TT,
		Optional<Reloc::Model> RM) {
	return Reloc::Static;
}

GenericFpgaTargetMachine::GenericFpgaTargetMachine(const Target &T,
		const Triple &TT, StringRef CPU, StringRef TuneCPU,
		const TargetOptions &Options, Optional<Reloc::Model> RM,
		Optional<CodeModel::Model> CM, CodeGenOpt::Level OL, bool JIT) :
		LLVMTargetMachine(T, computeDataLayout(TT), TT, CPU, TuneCPU, Options,
				getEffectiveRelocModel(TT, RM), CodeModel::Large, OL) {
	AsmInfo.reset(new llvm::MCAsmInfo());
}

GenericFpgaTargetMachine::~GenericFpgaTargetMachine() {
}

const GenericFpgaTargetSubtarget*
GenericFpgaTargetMachine::getSubtargetImpl(const Function &F) const {
	Attribute CPUAttr = F.getFnAttribute("target-cpu");
	Attribute TuneAttr = F.getFnAttribute("tune-cpu");
	Attribute FSAttr = F.getFnAttribute("target-features");

	std::string CPU =
			CPUAttr.isValid() ? CPUAttr.getValueAsString().str() : TargetCPU;
	std::string TuneCPU =
			TuneAttr.isValid() ? TuneAttr.getValueAsString().str() : CPU;
	std::string FS =
			FSAttr.isValid() ? FSAttr.getValueAsString().str() : TargetFS;
	std::string Key = CPU + TuneCPU + FS;
	auto &I = SubtargetMap[Key];
	if (!I) {
		// This needs to be done before we create a new subtarget since any
		// creation will depend on the TM and the code generation flags on the
		// function that reside in TargetOptions.
		resetTargetOptions(F);
		auto ABIName = Options.MCOptions.getABIName();
		if (const MDString *ModuleTargetABI = dyn_cast_or_null<MDString>(
				F.getParent()->getModuleFlag("target-abi"))) {
			ABIName = ModuleTargetABI->getString();
		}
		I = std::make_unique<GenericFpgaTargetSubtarget>(TargetTriple, CPU,
				TuneCPU, FS, ABIName, *this);
	}
	return I.get();

	// Attribute GenericFpgaAttr = F.getFnAttribute("target-cpu");
	//resetTargetOptions(F);
	//Subtarget(
	//				TT, CPU, TuneCPU, /*StringRef FS=*/"", PF, PD, /*const MCWriteProcResEntry */
	//				nullptr, /*const MCWriteLatencyEntry **/nullptr, /*const MCReadAdvanceEntry **/
	//				nullptr,
	//				/*const InstrStage **/nullptr, /*const unsigned *OC*/nullptr, /*const unsigned *FP*/
	//				nullptr)
}

TargetTransformInfo GenericFpgaTargetMachine::getTargetTransformInfo(
		const Function &F) {
	return TargetTransformInfo(GenericFpgaTTIImpl(this, F));
}

TargetPassConfig* GenericFpgaTargetMachine::createPassConfig(
		PassManagerBase &PM) {
	return new GenericFpgaTargetPassConfig(*this, PM);
}

}
