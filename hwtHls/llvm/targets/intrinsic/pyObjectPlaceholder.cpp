#include <hwtHls/llvm/targets/intrinsic/pyObjectPlaceholder.h>

namespace hwtHls {

const std::string PyObjectPlaceholderName = "hwtHls.pyObjectPlaceholder";
bool IsPyObjectPlacehoder(const llvm::CallInst *C) {
	return IsPyObjectPlacehoder(C->getCalledFunction());
}
bool IsPyObjectPlacehoder(const llvm::Function *F) {
	assert(
			F != nullptr
					&& "Function must have definition if input code was valid");
	return F->getName().str().rfind(PyObjectPlaceholderName, 0) == 0;
}

}

