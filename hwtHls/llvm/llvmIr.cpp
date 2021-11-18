#include "llvm/ADT/APInt.h"
#include "llvm/ADT/APSInt.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DerivedTypes.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Type.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IR/LegacyPassManager.h"
//#include "llvm/Passes/PassBuilder.h"

#include "llvm/Transforms/InstCombine/InstCombine.h"
#include "llvm/Transforms/Scalar.h"
#include "llvm/Transforms/Scalar/GVN.h"
#include "llvm/Transforms/Utils.h"

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include <iostream>

PYBIND11_MAKE_OPAQUE(std::vector<llvm::Type*>);

namespace py = pybind11;

// https://pybind11.readthedocs.io/en/stable/advanced/classes.html
// https://github.com/llvm/circt/blob/main/lib/Bindings/Python/MSFTModule.cpp
// https://blog.ekbana.com/write-a-python-binding-for-your-c-code-using-pybind11-library-ef0992d4b68
template<typename T>
std::string printToStr(T *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss);
	return ss.str();

}
//std::string Value__repr__(llvm::Value *self) {
//	return printToStr(self);
//}
//
//std::string IntegerType__repr__(llvm::IntegerType *self) {
//	std::string tmp;
//	llvm::raw_string_ostream ss(tmp);
//	self->print(ss);
//	return ss.str();
//}
//
std::string Module__repr__(llvm::Module *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss, nullptr);
	return ss.str();
}
std::string StringRef__repr__(llvm::StringRef *self) {
	return "<StringRef " + self->str() + ">";
}

std::string Twine__repr__(llvm::Twine *self) {
	return "<Twine " + self->str() + ">";
}
//std::string Function__repr__(llvm::Function *self) {
//	std::string tmp;
//	llvm::raw_string_ostream ss(tmp);
//	self->print(ss);
//	return ss.str();
//}

class LLVMStringContext {
	std::vector<std::string> _all_strings;
public:
	LLVMStringContext() {
	}
	llvm::StringRef addStringRef(const std::string &str) {
		// copy string to cache to make it persistent in C/C++
		_all_strings.push_back(str);
		return llvm::StringRef(_all_strings.back());
	}
	llvm::Twine addTwine(const std::string &str) {
		_all_strings.push_back(str);
		return llvm::Twine(_all_strings.back());
	}
};

PYBIND11_MODULE(toLlvm, m) {
	py::class_<llvm::Value, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
			.def("__repr__", &printToStr<llvm::Value>);
	py::class_<std::vector<llvm::Type*>>(m, "VectorOfTypePtr")
			.def(py::init<>())
			.def("clear", &std::vector<llvm::Type*>::clear)
			.def("pop_back", &std::vector<llvm::Type*>::pop_back)
			.def("push_back", [](std::vector<llvm::Type*> *self, llvm::Type *i) {
				return self->push_back(i);
			}, py::keep_alive<2, 1>()) /* Keep items alive while vector is used */
			.def("__len__", [](const std::vector<llvm::Type*> &v) {
				return v.size();
			})
			.def("__iter__", [](std::vector<llvm::Type*> &v) {
				return py::make_iterator(v.begin(), v.end());
			}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::StringRef>(m, "StringRef")
			.def("__repr__", &StringRef__repr__)
			.def("str", & llvm::StringRef::str);
	py::class_<llvm::Twine>(m, "Twine")
			.def("__repr__", &Twine__repr__)
			.def("str", & llvm::Twine::str);
	py::class_<LLVMStringContext>(m, "LLVMStringContext").def(py::init<>()).def(
			"addStringRef", &LLVMStringContext::addStringRef,
			py::return_value_policy::reference).def("addTwine",
			&LLVMStringContext::addTwine, py::return_value_policy::reference);

	// owned by context => no delete
	py::class_<llvm::Type, std::unique_ptr<llvm::Type, py::nodelete>>(m, "Type")
			.def("getVoidTy", &llvm::Type::getVoidTy, py::return_value_policy::reference)
			.def("getIntNTy", &llvm::Type::getIntNTy, py::return_value_policy::reference);


	py::class_<llvm::FunctionType>(m, "FunctionType")
			.def("get", [](llvm::Type *Result, const std::vector<llvm::Type*> &Params,
					bool isVarArg) {
				return llvm::FunctionType::get(Result, Params, isVarArg);
			}, py::return_value_policy::reference);
	py::class_<llvm::LLVMContext>(m, "LLVMContext")
			.def(py::init<>());
	py::class_<llvm::Module>(m, "Module")
			.def(py::init<llvm::StringRef, llvm::LLVMContext&>(), py::keep_alive<1, 2>(), py::keep_alive<1, 3>())
			.def("__repr__", &Module__repr__);
	py::class_<llvm::Function> Function(m, "Function");
	Function.def("__repr__",  &printToStr<llvm::Function>);
	Function.def("Create",
			[](llvm::FunctionType *Ty, llvm::Function::LinkageTypes Linkage,
					const llvm::Twine &N, llvm::Module &M) {
				return llvm::Function::Create(Ty, Linkage, N, M);
			}, //py::keep_alive<0, 1>(), py::keep_alive<0, 2>(),
			   //py::keep_alive<0, 3>(), py::keep_alive<0, 4>()
			py::return_value_policy::reference); /*keep dependencies alive while Function exists */
	Function.def("args",
			[](llvm::Function *self) {
				return py::make_iterator(self->arg_begin(), self->arg_end(),
						py::return_value_policy::reference);
			}, py::keep_alive<0, 1>()); /* Keep Function alive while iterator is used */
	py::class_<llvm::Argument, llvm::Value>(m, "Argument")
			.def("setName", &llvm::Argument::setName);

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

	py::class_<llvm::BasicBlock>(m, "BasicBlock")
			.def("Create", &llvm::BasicBlock::Create, py::return_value_policy::reference);

	py::class_<llvm::IRBuilder<>>(m, "IRBuilder")
			.def(py::init<llvm::LLVMContext&>())
			.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock *TheBB) {
				return self->SetInsertPoint(TheBB);
			}, py::return_value_policy::reference)
			.def("CreateAnd", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
					return self->CreateAnd(LHS, RHS, Name);
			}, py::return_value_policy::reference)
			.def("CreateOr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
					return self->CreateOr(LHS, RHS, Name);
			}, py::return_value_policy::reference)
			.def("CreateXor", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS, const llvm::Twine &Name = "") {
					return self->CreateXor(LHS, RHS, Name);
			}, py::return_value_policy::reference)
			.def("CreateAdd", &llvm::IRBuilder<>::CreateAdd, py::return_value_policy::reference)
			.def("CreateSub", &llvm::IRBuilder<>::CreateSub, py::return_value_policy::reference)
			.def("CreateMul", &llvm::IRBuilder<>::CreateMul, py::return_value_policy::reference);

	py::class_<llvm::IntegerType, llvm::Type>(m, "IntegerType")
			.def("getBitWidth", &llvm::IntegerType::getBitWidth)
			.def("__repr__",  &printToStr<llvm::IntegerType>);
	py::implicitly_convertible<llvm::IntegerType, llvm::Type>();


	m.def("errs", &llvm::errs);

	py::class_<llvm::APInt>(m, "APInt");
	py::class_<llvm::ConstantInt>(m, "ConstantInt");

	//py::class_<Dog, Animal>(m, "Dog").def(py::init<>());
	//m.def("call_go", &call_go);
}

