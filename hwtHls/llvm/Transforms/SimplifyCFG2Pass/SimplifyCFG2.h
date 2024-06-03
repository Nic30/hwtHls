#pragma once

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace hwtHls {


/// ValueEqualityComparisonCase - Represents a case of a switch.
struct ValueEqualityComparisonCase {
	llvm::ConstantInt *Value;
	llvm::BasicBlock *Dest;

	ValueEqualityComparisonCase(llvm::ConstantInt *Value, llvm::BasicBlock *Dest) :
			Value(Value), Dest(Dest) {
	}

	bool operator<(ValueEqualityComparisonCase RHS) const {
		// Comparing pointers is ok as we only rely on the order for uniquing.
		return Value < RHS.Value;
	}

	bool operator==(llvm::BasicBlock *RHSDest) const {
		return Dest == RHSDest;
	}
};

// original SimplifyCFGOpt with simplifySwitch/FoldValueComparisonIntoPredecessors patched
class SimplifyCFGOpt2 {
	llvm::DomTreeUpdater *DTU;
	const llvm::DataLayout &DL;
	const llvm::TargetTransformInfo &TTI;
	const SimplifyCFG2Options &Options;
	unsigned LlvmHoistCommonSkipLimit;

	bool Resimplify;

	llvm::Value* isValueEqualityComparison(llvm::Instruction *TI,
			bool checkParentPredecessors);
	llvm::BasicBlock* GetValueEqualityComparisonCases(llvm::Instruction *TI,
			std::vector<ValueEqualityComparisonCase> &Cases);
	bool FoldValueComparisonIntoPredecessors(llvm::Instruction *TI,
			llvm::IRBuilder<> &Builder);
	bool PerformValueComparisonIntoPredecessorFolding(llvm::Instruction *TI,
			llvm::Value *&CV, llvm::Instruction *PTI, llvm::IRBuilder<> &Builder);
	bool simplifySwitch(llvm::SwitchInst *SI, llvm::IRBuilder<> &Builder);
	bool simplifyBr(llvm::BranchInst *BI, llvm::IRBuilder<> &Builder);

public:
	SimplifyCFGOpt2(llvm::DomTreeUpdater *DTU, const llvm::DataLayout &DL,
			const llvm::TargetTransformInfo &TTI, const SimplifyCFG2Options &Opts,
			unsigned LlvmHoistCommonSkipLimit) :
			DTU(DTU), DL(DL), TTI(TTI), Options(Opts), LlvmHoistCommonSkipLimit(
					LlvmHoistCommonSkipLimit), Resimplify(false) {
		assert(
				(!DTU || !DTU->hasPostDomTree())
						&& "SimplifyCFG is not yet capable of maintaining validity of a "
								"PostDomTree, so don't ask for it.");
	}
	bool simplifyOnce(llvm::BasicBlock *BB);
	// Helper to set Resimplify and return change indication.
	bool requestResimplify() {
		Resimplify = true;
		return true;
	}
	bool run(llvm::BasicBlock *BB) {
		bool Changed = false;

		// Repeated simplify BB as long as resimplification is requested.
		do {
			Resimplify = false;

			// Perform one round of simplification. Resimplify flag will be set if
			// another iteration is requested.
			Changed |= simplifyOnce(BB);
		} while (Resimplify);

		return Changed;
	}
};

}
