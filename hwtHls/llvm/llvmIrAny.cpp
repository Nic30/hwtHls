#include <pybind11/detail/common.h>
#include <hwtHls/llvm/llvmIrAny.h>

#include <llvm/ADT/Any.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace py = pybind11;

namespace hwtHls {

template<typename T>
T* anyCaster(llvm::Any &V) {
	if (T **M = any_cast<T*>(&V)) {
		return *M;
	} else {
		return (T*) nullptr;
	}
}

void register_llvmAny(pybind11::module_ &m) {
	py::class_<llvm::Any, std::unique_ptr<llvm::Any, py::nodelete>> Any(m,
			"Any");
	m.def("AnyToFunction", &anyCaster<const llvm::Function>, py::return_value_policy::reference_internal);
	m.def("AnyToModule", &anyCaster<const llvm::Module>, py::return_value_policy::reference_internal);
	m.def("AnyToLoop", &anyCaster<const llvm::Loop>, py::return_value_policy::reference_internal);
	m.def("AnyToMachineFunction", &anyCaster<const llvm::MachineFunction>, py::return_value_policy::reference_internal);
}
}
