#pragma once

#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

namespace hwtHls {

struct ArgToAddToParentFn {
	llvm::AllocaInst *parentFnTmp;
	HwtHlsIoMetadata metadata;
};

// :param shouldUpdateOfOtherFnMd: :see: removeUnusedArgsOfParentFunction
llvm::Function& updateArgsOfParentFunction(llvm::IRBuilder<> &Builder,
		llvm::Function &F,
		const llvm::SmallVector<ArgToAddToParentFn> &argsToAddToParentFn,
		bool removeUnusedArgs = true,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd =
				{ });

// :param shouldUpdateOfOtherFnMd: function which specifies if the metadata of other function should be updated or not,
//        default value means "update all"
llvm::Function& removeUnusedArgsOfParentFunction(llvm::Function &F,
		std::optional<std::function<bool(const llvm::Function&)>> shouldUpdateOfOtherFnMd =
				{ });

}
