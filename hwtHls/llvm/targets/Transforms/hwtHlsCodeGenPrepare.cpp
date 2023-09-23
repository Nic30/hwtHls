#include <hwtHls/llvm/targets/Transforms/hwtHlsCodeGenPrepare.h>

namespace hwtHls {
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

}
