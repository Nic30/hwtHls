#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>

#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::tryReduceAndOfAssumedPredicates(
		llvm::BinaryOperator &I) {
	auto Ty = I.getType();
	if (!isa<IntegerType>(Ty) || Ty->getIntegerBitWidth() != 1)
		return nullptr;
	Value *andL, *andR;
	if (match(&I, m_And(m_Value(andL), m_Value(andR)))) {
		for (int i = 0; i < 2; ++i) { // loop for and operand commutativity
			// %2 = or i1 %0, %1
			// call void @llvm.assume(i1 %2)
			// %3 = xor i1 %1, true
			// %4 = and i1 %0, %3
			//
			// if %1==0 then %3==1 and %0 must be 1 (due to assume) and thus %4==1&1==1
			// if %1==1 then %3==0 and %4==0
			// this implies that %4==~%1=andR
			Value *v0 = andL, *v1;
			if (match(andR, m_Not(m_Value(v1)))) {
				if (auto impl = isImpliedConditionByAssume(v0, v1, AC, &DT,
						&I)) {
					if (impl.value() == false) {
						return replaceInstUsesWith(I, andR, true);
					}
				}
			}
			// if v0 ==> v1  then v0 & v1 == v0 because v1 is guaranteed to be 1 if v0 is 1
			if (auto impl = isImpliedConditionByAssume(andL, andR, AC, &DT,
					&I)) {
				if (impl.value()) {
					return replaceInstUsesWith(I, andL, true);
				}
			}

			std::swap(andL, andR);
		}
	}
	return nullptr;
}

}
