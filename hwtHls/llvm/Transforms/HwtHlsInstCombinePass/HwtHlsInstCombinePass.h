#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePassOptions.h>

namespace hwtHls {

/*
 * HwtHlsInstCombinePass does similar thing as llvm::InstCombinePass but it focuses
 * on more complex patterns and HwtHls intrinsic functions.
 * For more info :see: :class:`HwtHlsInstCombiner`.
 * */
class HwtHlsInstCombinePass: public llvm::PassInfoMixin<HwtHlsInstCombinePass> {
	HwtHlsInstCombinePassOptions Options;
public:
	static const std::string metadataName_mergableFunction_statePlusMaskedData;
	static const std::string metadataName_expr_maskContinuosFromLsb;
	
	HwtHlsInstCombinePass(HwtHlsInstCombinePassOptions Options =
			HwtHlsInstCombinePassOptions());
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
