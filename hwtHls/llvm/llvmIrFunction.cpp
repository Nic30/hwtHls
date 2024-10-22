#include <hwtHls/llvm/llvmIrFunction.h>

#include <algorithm>

#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Intrinsics.h>


#include <hwtHls/llvm/llvmIrCommon.h>
#include <hwtHls/llvm/llvmIrMetadata.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>

namespace py = pybind11;

namespace hwtHls {

template<typename T>
T* valueCaster(llvm::Value *V) {
	if (auto *_v = llvm::dyn_cast<T>(V)) {
		return _v;
	} else {
		return (T*) nullptr;
	}
}

void register_Function(pybind11::module_ & m) {
	py::class_<llvm::Function, std::unique_ptr<llvm::Function, py::nodelete>, llvm::GlobalValue> Function(m, "Function");
	Function.def("__repr__",  &printToStr<llvm::Function>)
		.def("Create",
			[](llvm::FunctionType *Ty, llvm::Function::LinkageTypes Linkage,
					const llvm::Twine &N, llvm::Module &M) {
				return llvm::Function::Create(Ty, Linkage, N, M);
			}, //py::keep_alive<0, 1>(), py::keep_alive<0, 2>(),
			   //py::keep_alive<0, 3>(), py::keep_alive<0, 4>()
			py::return_value_policy::reference_internal) /*keep dependencies alive while Function exists */
		.def("getGlobalIdentifier", [](llvm::Function *self) { return self->getGlobalIdentifier();})
		.def("getParent", [](llvm::Function & F) {return F.getParent();}, py::return_value_policy::reference_internal)
		.def("args", [](llvm::Function *self) {
				return py::make_iterator(self->arg_begin(), self->arg_end(),
						py::return_value_policy::reference);
			 }, py::keep_alive<0, 1>()) /* Keep Function alive while iterator is used */
		.def("arg_size", &llvm::Function::arg_size)
		.def("__iter__", [](llvm::Function &F) {
				return py::make_iterator(F.begin(), F.end());
			 }, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("getMetadata", [](llvm::Function * I, llvm::StringRef Kind) {
				return reinterpret_cast<MDNodeWithDeletedDelete*>(I->getMetadata(Kind));
		})
		.def("setMetadata", [](llvm::Function * F, llvm::StringRef Kind, MDNodeWithDeletedDelete *Node) {
			F->setMetadata(Kind, Node);
		})
		.def("getIntrinsicID", &llvm::Function::getIntrinsicID)
		.def("addFnAttrKind", [](llvm::Function*F, llvm::Attribute::AttrKind Attr) {
			F->addFnAttr(Attr);
		})
		.def("getEntryBlock", [](llvm::Function *self) {
			return &self->getEntryBlock();
		}, py::return_value_policy::reference_internal);

	m.def("ValueToFunction", &valueCaster<llvm::Function>);
	py::class_<llvm::Argument, std::unique_ptr<llvm::Argument, py::nodelete>, llvm::Value>(m, "Argument")
		.def("setName", &llvm::Argument::setName)
		.def("getName", &llvm::Argument::getName)
		.def("getType", &llvm::Argument::getType)
		.def("getArgNo", &llvm::Argument::getArgNo)
		;
	m.def("ValueToArgument", &valueCaster<llvm::Argument>);

	py::class_<llvm::Attribute, std::unique_ptr<llvm::Attribute, py::nodelete>> Attribute(m, "Attribute");
	py::enum_<llvm::Attribute::AttrKind> AttrKind(Attribute, "AttrKind");
	AttrKind.value("None",            llvm::Attribute::AttrKind::None           );
#define GET_ATTR_NAMES
#define _QUOTE(x) #x
#define ATTRIBUTE_ENUM(name, name_snakecase)  AttrKind.value(_QUOTE(name), llvm::Attribute::AttrKind::name);
#include <llvm/IR/Attributes.inc>
	AttrKind.export_values();

	m.def("AddDefaultFunctionAttributes", &AddDefaultFunctionAttributes);

	py::class_<llvm::FunctionCallee> FunctionCallee(m, "FunctionCallee");
	FunctionCallee.def(py::init<llvm::Function *>());

	auto Intrinsic = m.def_submodule("Intrinsic");
	py::enum_<llvm::Intrinsic::IndependentIntrinsics> IndependentIntrinsics(Intrinsic, "IndependentIntrinsics");
	for (unsigned I= llvm::Intrinsic::IndependentIntrinsics::abs; I <= llvm::Intrinsic::xray_typedevent; ++I) {
		auto _name = llvm::Intrinsic::getBaseName(I);
		assert(_name.starts_with("llvm."));
		std::string name = _name.substr(std::string("llvm.").length()).str();
		std::replace(name.begin(), name.end(), '.', '_');
		IndependentIntrinsics.value(name.c_str(), llvm::Intrinsic::IndependentIntrinsics(I));
	}
	IndependentIntrinsics.export_values();

}

}
