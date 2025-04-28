#include <hwtHls/llvm/Transforms/IcmpToOnlyEqLtLe.h>

#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/IRBuilder.h>
#include <algorithm>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

PreservedAnalyses IcmpToOnlyEqLtLePass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	std::vector<Instruction*> toRemove;
	for (BasicBlock &BB : F) {
		for (Instruction &I : BB) {
			if (auto *CMP = dyn_cast<ICmpInst>(&I)) {
				auto Name = CMP->getName();
				Value *LHS = CMP->getOperand(0);
				Value *RHS = CMP->getOperand(1);
				Value *replacement = nullptr;
				using Pred = ICmpInst::Predicate;
				switch (CMP->getPredicate()) {
				case Pred::ICMP_EQ:
				case Pred::ICMP_ULT:
				case Pred::ICMP_ULE:
				case Pred::ICMP_SLT:
				case Pred::ICMP_SLE:
					break;
				case Pred::ICMP_NE: { // a != b -> !(a == b)
					IRBuilder<> Builder(&I);
					auto eq = Builder.CreateICmpEQ(LHS, RHS);
					replacement = Builder.CreateNot(eq, Name);
					break;
				}
				case Pred::ICMP_UGT: {
					IRBuilder<> Builder(&I);
					if (isa<ConstantInt>(RHS)) {
						// a > b -> ~(a <= b)
						auto le = Builder.CreateICmpULE(LHS, RHS);
						replacement = Builder.CreateNot(le, Name);
					} else {
						// a > b -> b < a
						replacement = Builder.CreateICmpULT(RHS, LHS);
					}
					break;
				}
				case Pred::ICMP_UGE: {
					IRBuilder<> Builder(&I);
					if (isa<ConstantInt>(RHS)) {
						// a >= b -> ~(a < b)
						auto lt = Builder.CreateICmpULT(LHS, RHS);
						replacement = Builder.CreateNot(lt, Name);
					} else {
						//  a >=- b -> b <= a
						replacement = Builder.CreateICmpULE(RHS, LHS);
					}
					break;
				}

				case Pred::ICMP_SGT: {
					IRBuilder<> Builder(&I);
					if (isa<ConstantInt>(RHS)) {
						// a > b -> ~(a <= b)
						auto le = Builder.CreateICmpSLE(LHS, RHS);
						replacement = Builder.CreateNot(le, Name);
					} else {
						// a > b -> b < a
						replacement = Builder.CreateICmpSLT(RHS, LHS);
					}
					break;
				}
				case Pred::ICMP_SGE: {
					IRBuilder<> Builder(&I);
					if (isa<ConstantInt>(RHS)) {
						// a >= b -> ~(a < b)
						auto lt = Builder.CreateICmpSLT(LHS, RHS);
						replacement = Builder.CreateNot(lt, Name);
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
				if (replacement) {
					CMP->replaceAllUsesWith(replacement);
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
