#pragma once

#include <llvm/Analysis/LoopInfo.h>
#include <llvm/IR/Metadata.h>

namespace hwtHls {
llvm::MDNode* Loop_getHwtHlsLoopID(const llvm::Loop &L);
llvm::MDNode* findOptionMDForHwtHlsLoop(const llvm::Loop *TheLoop, llvm::StringRef Name);
std::optional<const llvm::MDOperand*> findStringMetadataForHwtHlsLoop(
		const llvm::Loop *TheLoop, llvm::StringRef Name);
std::optional<int> getOptionalIntHwtHlsLoopAttribute(const llvm::Loop *TheLoop,
		llvm::StringRef Name);
}
