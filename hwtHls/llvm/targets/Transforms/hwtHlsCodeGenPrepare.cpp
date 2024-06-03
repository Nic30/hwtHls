#include <hwtHls/llvm/targets/Transforms/hwtHlsCodeGenPrepare.h>

namespace hwtHls {
#define DEBUG_TYPE "hwtHls-code-gen-prepare"

bool HwtHlsCodeGenPrepare::optimizeSwitchType(SwitchInst *SI) {
  //Value *Cond = SI->getCondition();
  //if (!llvm::isa<llvm::ZExtInst>(Cond)) { // to prevent endless extension
//	  return CodeGenPrepare::optimizeSwitchType(SI);
  //}
  return false;
}
//bool HwtHlsCodeGenPrepare::optimizeSwitchInst(llvm::SwitchInst *SI) {
//	  bool Changed = optimizeSwitchType(SI);
//	  Changed |= optimizeSwitchPhiConstants(SI);
//	  return Changed;
//}
bool HwtHlsCodeGenPrepare::optimizeLoadExt(llvm::LoadInst *Load) {
	// the load data width is dependent on physical IO, can not optimize there or it is useless to optimize
	return false;
}

char HwtHlsCodeGenPrepareLegacyPass::ID = 0;

bool HwtHlsCodeGenPrepareLegacyPass::runOnFunction(Function &F) {
  if (skipFunction(F))
    return false;
  auto TM = &getAnalysis<TargetPassConfig>().getTM<TargetMachine>();
  HwtHlsCodeGenPrepare CGP(TM);
  CGP.DL = &F.getParent()->getDataLayout();
  CGP.SubtargetInfo = TM->getSubtargetImpl(F);
  CGP.TLI = CGP.SubtargetInfo->getTargetLowering();
  CGP.TRI = CGP.SubtargetInfo->getRegisterInfo();
  CGP.TLInfo = &getAnalysis<TargetLibraryInfoWrapperPass>().getTLI(F);
  CGP.TTI = &getAnalysis<TargetTransformInfoWrapperPass>().getTTI(F);
  CGP.LI = &getAnalysis<LoopInfoWrapperPass>().getLoopInfo();
  CGP.BPI.reset(new BranchProbabilityInfo(F, *CGP.LI));
  CGP.BFI.reset(new BlockFrequencyInfo(F, *CGP.BPI, *CGP.LI));
  CGP.PSI = &getAnalysis<ProfileSummaryInfoWrapperPass>().getPSI();
  auto BBSPRWP =
      getAnalysisIfAvailable<BasicBlockSectionsProfileReaderWrapperPass>();
  CGP.BBSectionsProfileReader = BBSPRWP ? &BBSPRWP->getBBSPR() : nullptr;

  return CGP._run(F);
}

INITIALIZE_PASS_BEGIN(HwtHlsCodeGenPrepareLegacyPass, DEBUG_TYPE,
                      "Optimize for code generation", false, false)
INITIALIZE_PASS_DEPENDENCY(BasicBlockSectionsProfileReaderWrapperPass)
INITIALIZE_PASS_DEPENDENCY(LoopInfoWrapperPass)
INITIALIZE_PASS_DEPENDENCY(ProfileSummaryInfoWrapperPass)
INITIALIZE_PASS_DEPENDENCY(TargetLibraryInfoWrapperPass)
INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
INITIALIZE_PASS_DEPENDENCY(TargetTransformInfoWrapperPass)
//INITIALIZE_PASS_END(CodeGenPrepareLegacyPass, DEBUG_TYPE,
//                    "Optimize for code generation", false, false)
//#define INITIALIZE_PASS_END(passName, arg, name, cfg, analysis)
  PassInfo *PI = new PassInfo(
  	  "Optimize for code generation", DEBUG_TYPE, &HwtHlsCodeGenPrepareLegacyPass::ID,
      PassInfo::NormalCtor_t(callDefaultCtor<HwtHlsCodeGenPrepareLegacyPass>), false, false);
  Registry.registerPass(*PI, true);
  return PI;
}
static llvm::once_flag InitializeHwtHlsCodeGenPrepareLegacyPassPassFlag;

void initializeHwtHlsCodeGenPrepareLegacyPassPass(PassRegistry &Registry) {
    llvm::call_once(InitializeHwtHlsCodeGenPrepareLegacyPassPassFlag,
    		hwtHls::initializeHwtHlsCodeGenPrepareLegacyPassPassOnce, std::ref(Registry));
}

HwtHlsCodeGenPrepareLegacyPass::HwtHlsCodeGenPrepareLegacyPass() : FunctionPass(ID) {
	 hwtHls::initializeHwtHlsCodeGenPrepareLegacyPassPass(*PassRegistry::getPassRegistry());
}


}
