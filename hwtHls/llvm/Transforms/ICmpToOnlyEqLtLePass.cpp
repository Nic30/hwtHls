#include <hwtHls/llvm/Transforms/ICmpToOnlyEqLtLePass.h>

#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/Analysis/InstSimplifyFolder.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>
#include <algorithm>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

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
					// x + c0 < c1
					// to
					// (x < (c1 - c0)) & (x > c0)   is smaller after offset substract, and offset substract does not underflow
					auto newO1 = c1->getValue() - c0->getValue();
					auto cmp = Builder.CreateICmpULT(x,
							ConstantInt::get(c0->getType(), newO1));
					auto overflowCheck = Builder.CreateICmpUGT(x, c0);
					return Builder.CreateAnd(cmp, overflowCheck);
				}
			}
		}
	}
	return nullptr;
}

PreservedAnalyses ICmpToOnlyEqLtLePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	std::vector<Instruction*> toRemove;
	auto &DL = F.getParent()->getDataLayout();
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
