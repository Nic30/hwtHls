#pragma once
#include <llvm/Support/ToolOutputFile.h>
#include <llvm/IR/LLVMContext.h>

namespace hwtHls {

std::unique_ptr<llvm::ToolOutputFile> LlvmCompilationBundle_registerORE(
		llvm::LLVMContext &Context);
}
