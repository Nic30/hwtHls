#pragma once
#include <map>
#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/LoopInfo.h>

namespace hwtHls {
/*
 * The parent PHI is associated with child PHI if:
 *  * it does not live trough child loop
 *  * has the same type
 *  * there is a path in expression from parent PHI to child PHI
 * */
std::map<llvm::PHINode*, llvm::PHINode*> findAssociatedPhis(llvm::Loop &LParent,
		llvm::Loop &LChild);
}
