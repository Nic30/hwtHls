#include <hwtHls/llvm/Transforms/ProfMetadataRmDummy.h>
#include <hwtHls/llvm/Transforms/ProfMetadataAddDummy.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/LLVMContext.h>

using namespace llvm;

#define DEBUG_TYPE "strip-dummy-prof-metadata"

STATISTIC(NumProfMetadataStriped, "Number removed dummy !prof metadata");

namespace hwtHls {

static bool stripProfMetadata(Function &F) {
	if (F.hasProfileData()
			&& F.hasMetadata(
					ProfMetadataAddDummy::METADATA_NAME_DUMMY_PROF_MD)) {
		F.setMetadata(llvm::LLVMContext::MD_prof, nullptr);
		F.setMetadata(ProfMetadataAddDummy::METADATA_NAME_DUMMY_PROF_MD,
				nullptr);
		++NumProfMetadataStriped;
		return true;
	}
	return false;
}

PreservedAnalyses ProfMetadataRmDummy::run(Module &M, ModuleAnalysisManager&) {
	for (Function &F : M) {
		stripProfMetadata(F);
	}

	return PreservedAnalyses::all();
}

llvm::PreservedAnalyses ProfMetadataRmDummy::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	stripProfMetadata(F);
	return PreservedAnalyses::all();
}

}
