#pragma once
#include "../../llvmSrc/CodeGenPrepare.h"

namespace hwtHls {

class HwtHlsCodeGenPrepare: public llvmSrc::CodeGenPrepare {
public:
	using llvmSrc::CodeGenPrepare::CodeGenPrepare;
	virtual bool optimizeSwitchInst(llvm::SwitchInst *SI) override;
	virtual bool optimizeLoadExt(llvm::LoadInst *Load)override;
};

}
