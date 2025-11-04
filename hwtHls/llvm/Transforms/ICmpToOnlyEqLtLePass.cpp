#include <hwtHls/llvm/Transforms/ICmpToOnlyEqLtLePass.h>

#include <algorithm>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/Analysis/InstSimplifyFolder.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

// :see:  LazyValueInfo.cpp, LazyValueInfoImpl::getValueFromSimpleICmpCondition

SmallVector<ConstantRange, 2> offsetAndSizeToRanges(APInt offset, APInt size) {
	// x + c0 < c1  ; c1 is range size; c0 is range offset
	//  < c1 selects the range <0, c0)
	//  + c0 shifts this range to <0-c0, -c0+c1) however the range may wrap around max or min val c0, c1
	//  For the left side of the selected range:
	SmallVector<ConstantRange, 2> ranges;
	if (size.isZero()) {
		// unsigned x + c0 < 0 selects an empty interval
		return ranges;
	}
	unsigned w = size.getBitWidth();
	APInt cMin(w, 0);
	auto cMax = APInt::getAllOnes(w);

	if (size == cMax) {
		// The range covers the entire space
		ranges.push_back(ConstantRange(cMin, cMax));
	} else {
		auto low = -offset;
		auto high = -offset + size;
		if (high.ugt(low)) {
			// No wrap around
			ranges.push_back(ConstantRange(low, high - 1));
		} else {
			// Wrap around case, from start to cMax and from cMin to high
			ranges.push_back(ConstantRange(low, cMax));
			ranges.push_back(ConstantRange(cMin, high - 1));
		}
	}
	return ranges;
}

Value* CreateRangeCheck(IRBuilderBase &Builder, Value*x, const APInt& low, const APInt& high) {
	Value * res = nullptr;
	if (!low.isZero()) {
		//res = Builder.CreateICmpUGE(x, low)
		// a >= b -> ~(a < b)  (to keep normal form of ICmpToOnlyEqLtLePass)
		auto lt = Builder.CreateICmpULT(x, Builder.getInt(low));
		res = Builder.CreateNot(lt);
	}
	if (!high.isAllOnes()) {
		auto highP1 = high + 1;
		auto lt = Builder.CreateICmpULT(x, Builder.getInt(highP1));
		if (res) {
			res = Builder.CreateAnd(res, lt);
		} else {
			res = lt;
		}
	}
	if (!res)
		return Builder.getTrue();
	return res;
}

Value* ICmpToOnlyEqLtLePass::_tryRewriteRangeCheckTo2xCmp(
		IRBuilderBase &Builder, ICmpInst &CMP) {
	Value *LHS = CMP.getOperand(0);
	Value *RHS = CMP.getOperand(1);
	using Pred = ICmpInst::Predicate;
	if (CMP.getPredicate() == Pred::ICMP_ULT) {
		if (auto c1 = dyn_cast<ConstantInt>(RHS)) {
			if (auto LHS_I = dyn_cast<Instruction>(LHS)) {
				Value *x;
				ConstantInt *c0;
				if (match(LHS_I, m_Add(m_Value(x), m_ConstantInt(c0)))) {
					auto offset = c0->getValue();
					auto size = c1->getValue();
					SmallVector<ConstantRange, 2> ranges = offsetAndSizeToRanges(offset, size);
					if (ranges.empty())
						return Builder.getFalse();
					Value * res = nullptr;
					for (const auto &r: ranges) {
						Value* rCmp = CreateRangeCheck(Builder, x, r.getLower(), r.getUpper());
						if (res) {
							res = Builder.CreateOr(res, rCmp);
						} else {
							res = rCmp;
						}
					}
					return res;
				}
			}
		}
	}
	return nullptr;
}

PreservedAnalyses ICmpToOnlyEqLtLePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	std::vector<Instruction*> toRemove;
	auto &DL = F.getDataLayout();
	IRBuilder<InstSimplifyFolder> Builder(F.getContext(),
			InstSimplifyFolder(DL));
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *CMP = dyn_cast<ICmpInst>(&I)) {
				Value *LHS = CMP->getOperand(0);
				Value *RHS = CMP->getOperand(1);

				Value *replacement = nullptr;
				Builder.SetInsertPoint(&I);
				if (rangeCmpWithoutAdd) {
					replacement = _tryRewriteRangeCheckTo2xCmp(Builder, *CMP);
				}
				if (!replacement) {
					using Pred = ICmpInst::Predicate;
					switch (CMP->getPredicate()) {
					case Pred::ICMP_EQ:
					case Pred::ICMP_ULT:
					case Pred::ICMP_ULE:
					case Pred::ICMP_SLT:
					case Pred::ICMP_SLE:
						break;
					case Pred::ICMP_NE: { // a != b -> !(a == b)
						auto eq = Builder.CreateICmpEQ(LHS, RHS);
						replacement = Builder.CreateNot(eq);
						break;
					}
					case Pred::ICMP_UGT: {
						if (isa<ConstantInt>(RHS)) {
							// a > b -> ~(a <= b)
							auto le = Builder.CreateICmpULE(LHS, RHS);
							replacement = Builder.CreateNot(le);
						} else {
							// a > b -> b < a
							replacement = Builder.CreateICmpULT(RHS, LHS);
						}
						break;
					}
					case Pred::ICMP_UGE: {
						if (isa<ConstantInt>(RHS)) {
							// a >= b -> ~(a < b)
							auto lt = Builder.CreateICmpULT(LHS, RHS);
							replacement = Builder.CreateNot(lt);
						} else {
							//  a >=- b -> b <= a
							replacement = Builder.CreateICmpULE(RHS, LHS);
						}
						break;
					}

					case Pred::ICMP_SGT: {
						if (isa<ConstantInt>(RHS)) {
							// a > b -> ~(a <= b)
							auto le = Builder.CreateICmpSLE(LHS, RHS);
							replacement = Builder.CreateNot(le);
						} else {
							// a > b -> b < a
							replacement = Builder.CreateICmpSLT(RHS, LHS);
						}
						break;
					}
					case Pred::ICMP_SGE: {
						if (isa<ConstantInt>(RHS)) {
							// a >= b -> ~(a < b)
							auto lt = Builder.CreateICmpSLT(LHS, RHS);
							replacement = Builder.CreateNot(lt);
						} else {
							//  a >=- b -> b <= a
							replacement = Builder.CreateICmpSLE(RHS, LHS);
						}
						break;
					}

					default:
						I.dump();
						llvm_unreachable("NotImplemented");
					}
				}
				if (replacement) {
					CMP->replaceAllUsesWith(replacement);
					CMP->takeName(replacement);
					toRemove.push_back(CMP);
				}
			}
		}
	}
	for (Instruction *I : toRemove) {
		I->eraseFromParent();
	}
	toRemove.clear();
	// Mark all the analyses that instcombine updates as preserved.
	PreservedAnalyses PA;
	PA.preserveSet<CFGAnalyses>();
	PA.preserve<AAManager>();
	PA.preserve<BasicAA>();
	PA.preserve<GlobalsAA>();
	return PA;
}
}
