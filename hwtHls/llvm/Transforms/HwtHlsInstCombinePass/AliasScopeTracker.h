#include <llvm/IR/Instruction.h>
#include <llvm/ADT/SmallPtrSet.h>


namespace hwtHls {

// copied from llvm-18 (not modified)
// Track the scopes used by !alias.scope and !noalias. In a function, a
// @llvm.experimental.noalias.scope.decl is only useful if that scope is used
// by both sets. If not, the declaration of the scope can be safely omitted.
// The MDNode of the scope can be omitted as well for the instructions that are
// part of this function. We do not do that at this point, as this might become
// too time consuming to do.
class AliasScopeTracker {
	llvm::SmallPtrSet<const llvm::MDNode*, 8> UsedAliasScopesAndLists;
	llvm::SmallPtrSet<const llvm::MDNode*, 8> UsedNoAliasScopesAndLists;

public:
	void analyse(llvm::Instruction *I);
	bool isNoAliasScopeDeclDead(llvm::Instruction *Inst);
};
}
