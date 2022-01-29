#pragma once
#include "genericFpgaSubtarget.h"
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/IR/DataLayout.h>
#include <llvm/Target/TargetMachine.h>

namespace llvm {

class StringRef;

/**
 * An LLVM representation of the target for an GenericFpga
 * */
class GenericFpgaTargetMachine final : public LLVMTargetMachine {
	mutable StringMap<std::unique_ptr<GenericFpgaSubtarget>> SubtargetMap;
public:
	GenericFpgaTargetMachine(const Target &T, const Triple &TT, StringRef CPU,
			StringRef FS, const TargetOptions &Options,
			Optional<Reloc::Model> RM, Optional<CodeModel::Model> CM,
			CodeGenOpt::Level OL, bool JIT);
	~GenericFpgaTargetMachine() override;
	const GenericFpgaSubtarget* getSubtargetImpl(const Function &F) const
			override;

	TargetTransformInfo getTargetTransformInfo(const Function &F) override;

	// Set up the pass pipeline.
	TargetPassConfig* createPassConfig(PassManagerBase &PM) override;
};

}

