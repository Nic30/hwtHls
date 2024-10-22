#include <hwtHls/llvm/llvmIrGlobalVariable.h>
#include <llvm/IR/GlobalVariable.h>
#include <llvm/IR/Module.h>

namespace py = pybind11;

namespace hwtHls {
void register_GlobalVariable(pybind11::module_ &m) {

	py::class_<llvm::Align> Align(m, "Align");
	Align.def(py::init<uint64_t>());

	py::class_<llvm::GlobalObject,
			std::unique_ptr<llvm::GlobalObject, py::nodelete>, llvm::GlobalValue> GlobalObject(
			m, "GlobalObject");
	GlobalObject.def("setAlignment",
			[](llvm::GlobalObject *self, llvm::Align Align) {
				self->setAlignment(Align);
			});

	py::class_<llvm::GlobalVariable,
			std::unique_ptr<llvm::GlobalVariable, py::nodelete>,
			llvm::GlobalObject> GlobalVariable(m, "GlobalVariable");
	// const llvm::Twine&, llvm::GlobalVariable*,
	// llvm::GlobalValue::ThreadLocalMode,
	// std::optional<unsigned int>, bool
	GlobalVariable //
	.def(
			py::init<llvm::Module&, llvm::Type*, bool,
					llvm::GlobalValue::LinkageTypes, llvm::Constant*>() //
			)//
	.def("setUnnamedAddr", &llvm::GlobalVariable::setUnnamedAddr);

}
}
