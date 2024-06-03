#pragma once
#include <hwtHls/llvm/llvmSrc/CodeGenPrepare.h>

namespace hwtHls {

class HwtHlsCodeGenPrepare: public llvmSrc::CodeGenPrepare {
	friend class HwtHlsCodeGenPrepareLegacyPass;
public:
	using llvmSrc::CodeGenPrepare::CodeGenPrepare;
	virtual bool optimizeSwitchType(SwitchInst *SI) override;
	//virtual bool optimizeSwitchInst(llvm::SwitchInst *SI) override;
	virtual bool optimizeLoadExt(llvm::LoadInst *Load)override;
	virtual ~HwtHlsCodeGenPrepare() {}
};

void initializeHwtHlsCodeGenPrepareLegacyPassPass(llvm::PassRegistry &Registry);


class HwtHlsCodeGenPrepareLegacyPass : public llvm::FunctionPass {
public:
  static char ID; // Pass identification, replacement for typeid

  HwtHlsCodeGenPrepareLegacyPass();
  bool runOnFunction(llvm::Function &F) override;

  StringRef getPassName() const override { return "hwtHls CodeGen Prepare"; }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    // FIXME: When we can selectively preserve passes, preserve the domtree.
    AU.addRequired<llvm::ProfileSummaryInfoWrapperPass>();
    AU.addRequired<llvm::TargetLibraryInfoWrapperPass>();
    AU.addRequired<llvm::TargetPassConfig>();
    AU.addRequired<llvm::TargetTransformInfoWrapperPass>();
    AU.addRequired<llvm::LoopInfoWrapperPass>();
    AU.addUsedIfAvailable<llvm::BasicBlockSectionsProfileReaderWrapperPass>();
  }
};

}
