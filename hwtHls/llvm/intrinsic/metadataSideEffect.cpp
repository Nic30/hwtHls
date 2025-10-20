#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>
#include <llvm/IR/Metadata.h>

namespace hwtHls {

const std::string METADATA_NAME_sideEffect_allowHoist =
		"hwthls.sideeffect.allowhoist";

void setMetadataSideeffectAllowHoist(llvm::Instruction &I) {
	I.setMetadata(METADATA_NAME_sideEffect_allowHoist,
			llvm::MDTuple::get(I.getContext(), { }));

}

bool hasMetadataSideeffectAllowHoist(llvm::Instruction &I) {
	return bool(I.getMetadata(METADATA_NAME_sideEffect_allowHoist));
}

}

