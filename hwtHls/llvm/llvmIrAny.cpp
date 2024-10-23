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
	m.def("AnyToFunction", &anyCaster<const llvm::Function>);
	m.def("AnyToModule", &anyCaster<const llvm::Module>);
	m.def("AnyToLoop", &anyCaster<const llvm::Loop>);
	m.def("AnyToMachineFunction", &anyCaster<const llvm::MachineFunction>);
}
}
