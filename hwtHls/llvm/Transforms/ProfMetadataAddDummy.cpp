#include <hwtHls/llvm/Transforms/ProfMetadataAddDummy.h>

using namespace llvm;

namespace hwtHls {

const std::string ProfMetadataAddDummy::METADATA_NAME_DUMMY_PROF_MD =
		"hwthls.prof.dummy";

static bool addDummyProfMd(Function &F) {
	if (!F.hasProfileData()) {
		F.setEntryCount(1); // set dummy profile metadata so BPI/BFI appear in loop passes and WriteGraph works
		F.setMetadata(ProfMetadataAddDummy::METADATA_NAME_DUMMY_PROF_MD,
				MDTuple::getDistinct(F.getContext(), { }));
		return true;
	}
	return false;
}

llvm::PreservedAnalyses ProfMetadataAddDummy::run(llvm::Module &M,
		llvm::ModuleAnalysisManager &AM) {
	for (auto &F : M) {
		addDummyProfMd(F);
	}
	return PreservedAnalyses::all();
}

llvm::PreservedAnalyses ProfMetadataAddDummy::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	addDummyProfMd(F);
	return PreservedAnalyses::all();
}

}
