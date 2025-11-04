#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/PatternMatch.h>
#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;
using namespace hwtHls::PatternMatch;

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::tryReduceAndWithEq_to_widerEq(
		llvm::BinaryOperator &I) {
	if (I.getType()->getScalarSizeInBits() != 1)
		return nullptr;
	Value * V0, *V1;
	size_t offset0, width0, offset1, width1;
	CmpPredicate Pred0;
	ConstantInt * C0;
	if (match(&I, m_And(m_ICmp(Pred0, m_BitrangeGet(m_Value(V0), offset0, width0), m_ConstantInt(C0)),
				        m_BitrangeGet(m_Value(V1), offset1, width1)
	)) && Pred0 == CmpInst::Predicate::ICMP_EQ && V0 == V1) {
		assert(width1 == 1 && "because it is operand of 1b and it must be 1b");
		auto c = C0->getValue().zext(width0 + width1);
		Value* src = nullptr;
		if (offset0 + width0 == offset1) {
			// e.g.  (x[8:0] == -1) & x[8] -> x[9:0] == -1
			c.setBit(width0);
			src = CreateBitRangeGetConst(&Builder, V0, offset0, width0+width1);
		} else if (offset1 + width1 == offset0) {
			// e.g.  x[0] & (x[8:1] == -1) -> x[8:0] == -1
			c = c.shl(width1);
			c.setBit(0);
			src = CreateBitRangeGetConst(&Builder, V0, offset1, width0+width1);
		}
		if (src) {
			Worklist.pushValue(src);
			Builder.SetInsertPoint(&I);
			auto r = Builder.CreateICmpEQ(src, Builder.getInt(c));
			// excludeAssumeUsers because AssumptionCache would not be able to recognize this in query for bits
			return replaceInstUsesWith(I, r, true);
		}
	}
	return nullptr;
}

}
