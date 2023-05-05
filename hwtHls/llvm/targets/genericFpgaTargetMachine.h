#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/ADT/Optional.h>
#include "genericFpgaTargetSubtarget.h"

namespace llvm {

class StringRef;

/**
 * An LLVM representation of the target for an GenericFpga
 * */
class GenericFpgaTargetMachine final : public llvm::LLVMTargetMachine {
	mutable llvm::StringMap<std::unique_ptr<GenericFpgaTargetSubtarget>> SubtargetMap;
public:
	GenericFpgaTargetMachine(const llvm::Target &T, const llvm::Triple &TT,
			llvm::StringRef CPU, llvm::StringRef FS,
			const llvm::TargetOptions &Options,
			std::optional<llvm::Reloc::Model> RM,
			std::optional<llvm::CodeModel::Model> CM,
			llvm::CodeGenOpt::Level OL, bool JIT);
	~GenericFpgaTargetMachine() override;
	const GenericFpgaTargetSubtarget* getSubtargetImpl(
			const llvm::Function &F) const override;
	llvm::TargetTransformInfo getTargetTransformInfo(const llvm::Function &F) const
			override;
	// Set up the pass pipeline.
	llvm::TargetPassConfig* createPassConfig(llvm::PassManagerBase &PM)
			override;
};

}

