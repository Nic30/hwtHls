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

bool extractBitsIfExtractInstrAlreadyExits(Value *V,
		SmallVector<Value*> &bitsOfVLsbFirst) {
	// errs() << "extractBitsIfExtractInstrAlreadyExits: " << *V << "\n";
	assert(V->getType()->isIntegerTy());
	size_t width = V->getType()->getIntegerBitWidth();
	if (width == 1) {
		bitsOfVLsbFirst.push_back(V);
		return true;
	} else if (auto I = dyn_cast<Instruction>(V)) {
		if (isa<ZExtInst>(I)) {
			if (!extractBitsIfExtractInstrAlreadyExits(I->getOperand(0), bitsOfVLsbFirst))
				return false;
			// pad with zeros
			auto b0 = ConstantInt::get(IntegerType::get(V->getContext(), 1), 0);
			for (size_t i = I->getOperand(0)->getType()->getIntegerBitWidth();
					i < width; i++) {
				bitsOfVLsbFirst.push_back(b0);
			}
			return true;
		} else if (isa<SExtInst>(I)) {
			if (!extractBitsIfExtractInstrAlreadyExits(I->getOperand(0), bitsOfVLsbFirst))
				return false;
			auto msb = bitsOfVLsbFirst.back();
			// pad with msb
			for (size_t i = I->getOperand(0)->getType()->getIntegerBitWidth();
					i < width; i++) {
				bitsOfVLsbFirst.push_back(msb);
			}
			return true;
		} else if (auto CI = dyn_cast<CallInst>(I)) {
			if (IsBitConcat(CI)) {
				for (auto &argOp : CI->args()) {
					if (!extractBitsIfExtractInstrAlreadyExits(argOp,
							bitsOfVLsbFirst)) {
						return false;
					}
				}
				return true;
			} else if (IsBitRangeGet(CI)) {
				auto srcI = dyn_cast<Instruction>(CI->getArgOperand(0));
				if (!srcI)
					return false;
				auto off = BitRangeGetOffset(CI);
				for (size_t i = 0; i < width; i++) {
					// try search slice on src operand of this slice
					auto b = SearchBitRangeGetConst(srcI, i + off, 1);
					if (!b)
						return false;
					bitsOfVLsbFirst.push_back(b);
				}
				return true;
			} else {
				// try search for 1b slices on this instruction
				for (size_t i = 0; i < width; i++) {
					auto b = SearchBitRangeGetConst(I, i, 1);
					if (!b)
						return false;
					bitsOfVLsbFirst.push_back(b);
				}
				return true;
			}
		}
	} else if (auto C = dyn_cast<ConstantInt>(V)) {
		auto b1t = IntegerType::get(V->getContext(), 1);
		auto b0 = ConstantInt::get(b1t, 0);
		auto b1 = ConstantInt::get(b1t, 1);
		auto &v = C->getValue();
		for (size_t i = 0; i < width; i++) {
			if (v.extractBitsAsZExtValue(1, i)) {
				bitsOfVLsbFirst.push_back(b1);
			} else {
				bitsOfVLsbFirst.push_back(b0);
			}
		}
		return true;
	}
	return false;
}

llvm::Instruction* HwtHlsInstCombiner::tryReduceOrOfAssumedPredicates(
		llvm::BinaryOperator &I) {
	auto Ty = I.getType();
	if (!isa<IntegerType>(Ty))
		return nullptr;

	Value *orL, *orR;
	if (match(&I, m_Or(m_Value(orL), m_Value(orR)))) {
		// We can replace with orL only if the orL is generalization of orR
		// that means (orR ==> orL)  (orL if orR )
		if (I.getType()->isIntegerTy(1)) {
			// single bit variant

			for (int i = 0; i < 2; ++i) { // loop for and operand commutativity
				if (i == 1)
					std::swap(orL, orR);

				if (auto impl = isImpliedConditionAndOrTree(Builder, orR, orL,
						DL, &AC, &DT, &I)) {
					if (!impl.value())
						continue;
					return replaceInstUsesWith(I, orL, true);
				}
			}
		} else {
			// multi bit variant, check on per bit basis, but allow orL only to be sext of i1
			// to not trigger this opt on every or from performance reasons
			Value *_c0;
			if (!match(orL, m_SExt(m_Value(_c0)))
					|| !_c0->getType()->isIntegerTy(1))
				if (!match(orR, m_SExt(m_Value(_c0)))
						|| !_c0->getType()->isIntegerTy(1))
					return nullptr;
			// %orL = sext i1 %c0 to i3
			// %orR = call i3 @hwtHls.bitConcat.*(....)
			// %I = or i3 %orL, %orR
			SmallVector<Value*> orLbitsLsbFirst;
			SmallVector<Value*> orRbitsLsbFirst;
			SmallVector<Value*> resultLsbFirst;
			if (!extractBitsIfExtractInstrAlreadyExits(orL, orLbitsLsbFirst))
				return nullptr;
			if (!extractBitsIfExtractInstrAlreadyExits(orR, orRbitsLsbFirst))
				return nullptr;

			for (int i = 0; i < 2; ++i) { // loop for and operand commutativity
				if (i == 1) {
					std::swap(orL, orR);
					std::swap(orLbitsLsbFirst, orRbitsLsbFirst);
				}
				bool matched = true;
				for (const auto& [orLbit, orRbit] : zip(orLbitsLsbFirst,
						orRbitsLsbFirst)) {
					// errs() << "orLbit " << *orLbit << "\n";
					// errs() << "orRbit " << *orRbit << "\n";
					if (match(orRbit, m_SpecificInt(1))) {
						resultLsbFirst.push_back(orLbit);
					} else if (auto impl = isImpliedConditionAndOrTree(Builder,
							orRbit, orLbit, DL, &AC, &DT, &I)) {
						// check orR bit==>orL bit
						if (!impl.value()) {
							// errs() << "[does not imply]\n";
							matched = false;
							break;
						}
						resultLsbFirst.push_back(orRbit);
					} else {
						// errs() << "[does not know if implies]\n";
						matched = false;
						break;
					}
				}
				if (!matched)
					continue;
				// for (auto b : resultLsbFirst) {
				// 	errs() << "b: " << *b << "\n";
				// }
				auto replacement = CreateBitConcat(&Builder, resultLsbFirst);
				return replaceInstUsesWith(I, replacement, true);
			}
		}
	}

	return nullptr;
}

}
