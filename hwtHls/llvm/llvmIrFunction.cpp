#include "llvmIrFunction.h"

#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>


#include "llvmIrCommon.h"
#include "llvmIrMetadata.h"

namespace py = pybind11;

namespace hwtHls {

void register_Function(pybind11::module_ & m) {
	py::class_<llvm::Function, std::unique_ptr<llvm::Function, py::nodelete>, llvm::GlobalValue> Function(m, "Function");
	Function.def("__repr__",  &printToStr<llvm::Function>)
		.def("Create",
			[](llvm::FunctionType *Ty, llvm::Function::LinkageTypes Linkage,
					const llvm::Twine &N, llvm::Module &M) {
				return llvm::Function::Create(Ty, Linkage, N, M);
			}, //py::keep_alive<0, 1>(), py::keep_alive<0, 2>(),
			   //py::keep_alive<0, 3>(), py::keep_alive<0, 4>()
			py::return_value_policy::reference) /*keep dependencies alive while Function exists */
		.def("getGlobalIdentifier", [](llvm::Function *self) { return self->getGlobalIdentifier();})
		.def("args", [](llvm::Function *self) {
				return py::make_iterator(self->arg_begin(), self->arg_end(),
						py::return_value_policy::reference);
			 }, py::keep_alive<0, 1>()) /* Keep Function alive while iterator is used */
		.def("__iter__", [](llvm::Function &F) {
				return py::make_iterator(F.begin(), F.end());
			 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("setMetadata", [](llvm::Function * F, llvm::StringRef Kind, MDNodeWithDeletedDelete *Node) {
			F->setMetadata(Kind, Node);
		});
	py::class_<llvm::Argument, std::unique_ptr<llvm::Argument, py::nodelete>, llvm::Value>(m, "Argument")
		.def("setName", &llvm::Argument::setName)
		.def("getName", &llvm::Argument::getName)
		.def("getType", &llvm::Argument::getType)
		;

	py::enum_<llvm::Function::LinkageTypes>(Function, "LinkageTypes")
		.value("ExternalLinkage",            llvm::Function::LinkageTypes::ExternalLinkage           )
		.value("AvailableExternallyLinkage", llvm::Function::LinkageTypes::AvailableExternallyLinkage)
		.value("LinkOnceAnyLinkage",         llvm::Function::LinkageTypes::LinkOnceAnyLinkage        )
		.value("LinkOnceODRLinkage",         llvm::Function::LinkageTypes::LinkOnceODRLinkage        )
		.value("WeakAnyLinkage",             llvm::Function::LinkageTypes::WeakAnyLinkage            )
		.value("WeakODRLinkage",             llvm::Function::LinkageTypes::WeakODRLinkage            )
		.value("AppendingLinkage",           llvm::Function::LinkageTypes::AppendingLinkage          )
		.value("InternalLinkage",            llvm::Function::LinkageTypes::InternalLinkage           )
		.value("PrivateLinkage",             llvm::Function::LinkageTypes::PrivateLinkage            )
		.value("ExternalWeakLinkage",        llvm::Function::LinkageTypes::ExternalWeakLinkage       )
		.value("CommonLinkage",              llvm::Function::LinkageTypes::CommonLinkage             )
		.export_values();
}

}
