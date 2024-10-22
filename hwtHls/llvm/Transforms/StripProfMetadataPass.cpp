#include <hwtHls/llvm/Transforms/StripProfMetadataPass.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/LLVMContext.h>

using namespace llvm;

#define DEBUG_TYPE "strip-prof-metadata"

STATISTIC(NumProfMetadataStriped, "Number removed !prof metadata");

namespace hwtHls {

static bool stripProfMetadata(Function &F) {
	if (F.hasProfileData()) {
		F.setMetadata(llvm::LLVMContext::MD_prof, nullptr);
		++NumProfMetadataStriped;
		return true;
	}
	return false;
}

PreservedAnalyses StripProfMetadataPass::run(Module &M,
		ModuleAnalysisManager&) {
	bool MadeChange = false;

	for (Function &F : M) {
		MadeChange |= stripProfMetadata(F);
	}

	if (MadeChange)
		return PreservedAnalyses::none();
	return PreservedAnalyses::all();
}

llvm::PreservedAnalyses StripProfMetadataPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {

	if (stripProfMetadata(F))
		return PreservedAnalyses::none();
	return PreservedAnalyses::all();
}

}
