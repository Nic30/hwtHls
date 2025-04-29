#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombiner.h>

#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/PatternMatch.h>
#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;
using namespace hwtHls::PatternMatch;

// https://www.emathhelp.net/calculators/discrete-mathematics/boolean-algebra-calculator/

namespace hwtHls {

llvm::Instruction* HwtHlsInstCombiner::tryReduceAndAndWithCommon(
		llvm::BinaryOperator &I) {
	// %9 = and i1 %a, %b
	// %14 = and i1 %a, %c
	// %29 = xor i1 %9, true
	// %30 = xor i1 %14, true
	// %32 = and i1 %29, %30
	//  (~(a & b) & ~(a & c)) == (~a | (~b & ~c)) == (~a | ~(b | c)) == ~(a & (b | c))

	Value *l0, *l1, *r0, *r1;
	if (match(&I,
			m_And(m_Not(m_And(m_Value(l0), m_Value(l1))),
					m_Not(m_And(m_Value(r0), m_Value(r1)))))) {
		for (int i = 0; i < 2; ++i) { // loop for left and operand commutativity
			Value *a = l0, *b = l1, *c = nullptr;
			if (l0 == r0) {
				c = r1;
			} else if (l0 == r1) {
				c = r0;
			}
			if (c) {
				Builder.SetInsertPoint(&I);
				auto bOrC = Builder.CreateOr(b, c);
				Worklist.pushValue(bOrC);
				auto aAndBOrC = Builder.CreateAnd(a, bOrC);
				Worklist.pushValue(aAndBOrC);
				auto notAAndBOrC = Builder.CreateNot(aAndBOrC);
				Worklist.pushValue(notAAndBOrC);
				return replaceInstUsesWith(I, notAAndBOrC);
			}
			std::swap(l0, l1);
		}
	}
	// %20 = and i1 %9, %19
	// %25 = and i1 %9, %24
	// %71 = or i1 %20, %25
	// ((a & b) | (a & c)) == (a & (b | c))
	if (match(&I,
			m_Or(m_And(m_Value(l0), m_Value(l1)),
					m_And(m_Value(r0), m_Value(r1))))) {
		for (int i = 0; i < 2; ++i) { // loop for left and operand commutativity
			Value *a = l0, *b = l1, *c = nullptr;
			if (l0 == r0) {
				c = r1;
			} else if (l0 == r1) {
				c = r0;
			}
			if (c) {
				Builder.SetInsertPoint(&I);
				auto bOrC = Builder.CreateOr(b, c);
				Worklist.pushValue(bOrC);
				auto AAndBOrC = Builder.CreateAnd(a, bOrC);
				Worklist.pushValue(AAndBOrC);
				return replaceInstUsesWith(I, AAndBOrC);
			}
			std::swap(l0, l1);
		}
	}

	//%.241 = and i1 %55, %.039
	//%54 = and i1 %9, %53
	//%55 = xor i1 %54, true

	//%16 = call i4 @hwtHls.bitRangeGet.i73.i8.i4.65(i73 %.w0, i8 65) #6
	//  %38 = icmp ne i2 %28, -1
	//  %39 = and i1 %16, %38
	//  %40 = xor i1 %39, true
    //
	//  %13 = call i1 @hwtHls.bitRangeGet.i73.i8.i1.66(i73 %.w0, i8 66) #6
	//  %37 = icmp ult i10 %34, 128
	//  %wEn3.2 = and i1 %13, %37
    //
	//  %.streamWrite.en19.2 = and i1 %wEn3.2, %40

	return nullptr;
}

struct NegatedSliceInfo {
	Value *src;
	bool isNegated;
	size_t offset;
	size_t width;
	NegatedSliceInfo() :
			src(nullptr), isNegated(false), offset(0), width(0) {
	}
	bool isDirectlyBefore(const NegatedSliceInfo &other) const {
		return src == other.src && offset + width == other.offset;
	}

	bool isValid() const {
		return src != nullptr;
	}
	static NegatedSliceInfo fromValue(Value *V) {
		NegatedSliceInfo res;
		if (match(V, m_BitrangeGet(m_Value(res.src), res.offset, res.width))) {
			res.isNegated = false;
		} else if (match(V,
				m_Not(
						m_BitrangeGet(m_Value(res.src), res.offset,
								res.width)))) {
			res.isNegated = true;
		} else {
			res.src = nullptr;
		}
		return res;
	}
};

llvm::Instruction* HwtHlsInstCombiner::tryReduceOrOnBits_toNE(
		llvm::BinaryOperator &I) {
	if (!I.getType()->isIntegerTy(1))
		return nullptr;
	Instruction *v0;
	Instruction *v1;
	ICmpInst::Predicate Pred;
	ConstantInt *CI0 = nullptr;
	ConstantInt *CI1 = nullptr;
	NegatedSliceInfo slice0;
	NegatedSliceInfo slice1;
	if (match(&I,
			m_c_Or(m_Instruction(v0),
					m_ICmp(Pred,
							m_BitrangeGet(m_Value(slice1.src), slice1.offset,
									slice1.width), m_ConstantInt(CI1))))) {
		if (Pred != ICmpInst::Predicate::ICMP_NE)
			return nullptr;
		// x[0] | x[3:1] != 0 -> x[0:0] != 0 with support for negation of term and any index
		slice0 = NegatedSliceInfo::fromValue(v0);
	} else if (match(&I, m_Or(m_Instruction(v0), m_Instruction(v1)))) {
		// x[0] | x[1] -> x[1:0] != 0 with support for negation of term and any index
		slice0 = NegatedSliceInfo::fromValue(v0);
		if (!slice0.isValid())
			return nullptr;
		slice1 = NegatedSliceInfo::fromValue(v1);
	}
	if (slice0.isValid() && slice1.isValid()) {
		if (slice0.src != slice1.src) {
			return nullptr;
		}
		for (int i = 0; i < 2; ++i) { // loop to implement commutativity
			if (slice0.isDirectlyBefore(slice1)) {
				APInt cmpNeRhs = APInt::getZero(slice0.width + slice1.width);
				if (slice0.isNegated) {
					assert(CI0 == nullptr);
					assert(slice0.width == 1);
					cmpNeRhs.setBit(0);
				} else if (CI0) {
					cmpNeRhs |= CI0->getValue().zext(cmpNeRhs.getBitWidth());
				}
				// else keep cmpNeRhs[0] == 0
				if (slice1.isNegated) {
					assert(CI1 == nullptr);
					assert(slice1.width == 1);
					cmpNeRhs.setBit(slice0.width);
				} else if (CI1) {
					cmpNeRhs |= (CI1->getValue().zext(cmpNeRhs.getBitWidth())
							<< slice0.width);
				}
				// else keep cmpNeRhs[slice0.width] == 0

				Value *vSlice = CreateBitRangeGetConst(&Builder, slice0.src,
						slice0.offset, cmpNeRhs.getBitWidth());
				Worklist.pushValue(vSlice);
				auto r = Builder.CreateICmpNE(vSlice, Builder.getInt(cmpNeRhs));
				return replaceInstUsesWith(I, r);
			}
			std::swap(slice0, slice1);
			std::swap(CI0, CI1);
		}
	}
	return nullptr;
}

}
