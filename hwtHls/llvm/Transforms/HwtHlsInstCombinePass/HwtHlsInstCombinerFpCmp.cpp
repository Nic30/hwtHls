#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>

using namespace llvm;

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::_tryReduceHwtHlsFCmp(llvm::CallInst &I) {
	// discard checks for NaN/Inf on types which do not support NaN
	auto _p = dyn_cast<ConstantInt>(I.getArgOperand(0));
	assert(_p);
	auto p = CmpInst::Predicate(_p->getZExtValue());
	switch (p) {
	case CmpInst::Predicate::FCMP_ORD:
	case CmpInst::Predicate::FCMP_UNO: {
		auto cfg = HFloatTmpConfig::fromCallArgs(I, 1 + 2);
		if (cfg.isInQFormat && !cfg.hasIsInf && !cfg.hasIsNaN) {
			bool replacement = p == CmpInst::Predicate::FCMP_ORD;
			return replaceInstUsesWith(I, Builder.getInt1(replacement));
		}
		break;
	}
	default:
		break;
	}
	return nullptr;
}

}
