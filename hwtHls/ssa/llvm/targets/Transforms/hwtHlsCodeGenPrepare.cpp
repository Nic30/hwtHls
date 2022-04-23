#include "hwtHlsCodeGenPrepare.h"

namespace hwtHls {

bool HwtHlsCodeGenPrepare::optimizeSwitchInst(llvm::SwitchInst *SI) {
	// disable because we never have to extend the switch on variable
	return false;
}
bool HwtHlsCodeGenPrepare::optimizeLoadExt(llvm::LoadInst *Load) {
	// the load data width is dependent on physical IO, can not optimize there or it is useless to optimize
	return false;
}

}
