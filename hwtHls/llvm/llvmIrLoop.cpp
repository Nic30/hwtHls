#include <hwtHls/llvm/llvmIrLoop.h>

#include <hwtHls/llvm/llvmIrCommon.h>
#include <llvm/Analysis/LoopInfo.h>

namespace py = pybind11;

namespace hwtHls {

void register_Loop(pybind11::module_ &m) {
	py::class_<llvm::Loop, std::unique_ptr<llvm::Loop, py::nodelete>> Loop(m, "Loop");
	Loop.def("__repr__",  &printToStr<llvm::Loop>)
		.def("getHeader", &llvm::Loop::getHeader, py::return_value_policy::reference_internal);
}

}
