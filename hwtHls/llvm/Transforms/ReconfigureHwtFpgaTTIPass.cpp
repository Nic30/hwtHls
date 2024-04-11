#include <hwtHls/llvm/Transforms/ReconfigureHwtFpgaTTIPass.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

namespace hwtHls {

llvm::PreservedAnalyses ReconfigureHwtFpgaTTIPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	auto HwtFpgaTM = dynamic_cast<llvm::HwtFpgaTargetMachine*>(TM);
	assert(HwtFpgaTM);
	if (AllowVolatileMemOpDuplication.has_value())
		HwtFpgaTM->setAllowVolatileMemOpDuplication(
				AllowVolatileMemOpDuplication.value());
	return llvm::PreservedAnalyses::all();
}

}

