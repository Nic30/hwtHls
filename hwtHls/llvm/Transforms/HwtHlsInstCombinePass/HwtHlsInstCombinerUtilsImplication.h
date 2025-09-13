#pragma once

#include <optional>
#include <llvm/ADT/SmallVector.h>

namespace llvm {
class Value;
class Instruction;
class DataLayout;
class AssumptionCache;
class DominatorTree;
class IRBuilderBase;
}

namespace hwtHls {

extern const std::string IMPLICATION_CACHE_INSTR_NAME_PREFIX;
// :see: llvm::isImpliedCondition
std::optional<bool> isImpliedConditionAndOrTree(llvm::IRBuilderBase &Builder,
		llvm::Value *LHS, llvm::Value *RHS, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, const llvm::DominatorTree *DT,
		const llvm::Instruction *CtxI);

// :returns: true if LHS==>RHS, false if (~LHS)==>RHS
std::optional<bool> isImpliedConditionByAssume(const llvm::Value *LHS,
		const llvm::Value *RHS, llvm::AssumptionCache &AC,
		const llvm::DominatorTree *DT, const llvm::Instruction *CtxI);

void pruneImpliedConditionsAndLastLikelyMostSpecific(
		llvm::SmallVector<llvm::Value*> &conditionsForAnd,
		llvm::IRBuilderBase &Builder, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, const llvm::DominatorTree *DT,
		const llvm::Instruction *CtxI);
}
