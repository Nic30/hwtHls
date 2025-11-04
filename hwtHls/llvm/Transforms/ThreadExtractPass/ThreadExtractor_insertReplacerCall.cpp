#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractor.h>

using namespace llvm;

#define DEBUG_TYPE "hwtHls::ThreadExtractor"

namespace hwtHls {

void HwtHlsCodeExtractor::insertReplacerCall(Function *oldFunction,
		BasicBlock *header, BasicBlock *codeReplacer, const ValueSet &outputs,
		ArrayRef<Value*> Reloads,
		const DenseMap<BasicBlock*, BlockFrequency> &ExitWeights) {
	llvmSrc::CodeExtractor::insertReplacerCall(oldFunction, header, codeReplacer,
			outputs, Reloads, ExitWeights);

	//IRBuilder<> Builder(oldFunction->getContext());
	//if (beginSyncAlloca) {
	//	Type *Ty1b = Builder.getIntNTy(1);
	//	Builder.SetInsertPoint(codeReplacer); // write to inputs before extracted section
	//	Builder.CreateStore(ConstantInt::get(Ty1b, 1), beginSyncAlloca, /*isVolatile*/
	//	true);
	//}
}

}
