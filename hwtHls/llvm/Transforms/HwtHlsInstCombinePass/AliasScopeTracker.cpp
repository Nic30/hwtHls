#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/AliasScopeTracker.h>
#include <llvm/Support/Casting.h>
#include <llvm/IR/Metadata.h>
#include <llvm/IR/IntrinsicInst.h>

// copied from llvm-18 (not modified)
using namespace llvm;

namespace hwtHls {
void AliasScopeTracker::analyse(llvm::Instruction *I) {
	// This seems to be faster than checking 'mayReadOrWriteMemory()'.
	if (!I->hasMetadataOtherThanDebugLoc())
		return;

	auto Track = [](llvm::Metadata *ScopeList, auto &Container) {
		const auto *MDScopeList = llvm::dyn_cast_or_null<llvm::MDNode>(
				ScopeList);
		if (!MDScopeList || !Container.insert(MDScopeList).second)
			return;
		for (const auto &MDOperand : MDScopeList->operands())
			if (auto *MDScope = llvm::dyn_cast<llvm::MDNode>(MDOperand))
				Container.insert(MDScope);
	};

	Track(I->getMetadata(llvm::LLVMContext::MD_alias_scope),
			UsedAliasScopesAndLists);
	Track(I->getMetadata(llvm::LLVMContext::MD_noalias),
			UsedNoAliasScopesAndLists);
}

bool AliasScopeTracker::isNoAliasScopeDeclDead(llvm::Instruction *Inst) {
	llvm::NoAliasScopeDeclInst *Decl =
			llvm::dyn_cast<llvm::NoAliasScopeDeclInst>(Inst);
	if (!Decl)
		return false;

	assert(
			Decl->use_empty()
					&& "llvm.experimental.noalias.scope.decl in use ?");
	const llvm::MDNode *MDSL = Decl->getScopeList();
	assert(
			MDSL->getNumOperands() == 1
					&& "llvm.experimental.noalias.scope should refer to a single scope");
	auto &MDOperand = MDSL->getOperand(0);
	if (auto *MD = llvm::dyn_cast<llvm::MDNode>(MDOperand))
		return !UsedAliasScopesAndLists.contains(MD)
				|| !UsedNoAliasScopesAndLists.contains(MD);

	// Not an MDNode ? throw away.
	return true;
}
}
