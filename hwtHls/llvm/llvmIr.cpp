#include "llvmIrCommon.h"
#include "llvmIrBuilder.h"
#include "llvmIrInstruction.h"
#include "llvmIrStrings.h"
#include "llvmIrValues.h"
#include "llvmIrMachineFunction.h"
#include "llvmCompilationBundle.h"
#include "targets/genericFpga.h"
#include "targets/Transforms/genericFpgaToNetlist.h"

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/CodeGen/MachineInstr.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <memory>
#include <string>
#include <vector>


PYBIND11_MAKE_OPAQUE(std::vector<llvm::Type*>);

namespace py = pybind11;

// https://pybind11.readthedocs.io/en/stable/advanced/classes.html
// https://github.com/llvm/circt/blob/main/lib/Bindings/Python/MSFTModule.cpp
// https://blog.ekbana.com/write-a-python-binding-for-your-c-code-using-pybind11-library-ef0992d4b68


std::string Module__repr__(llvm::Module *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss, nullptr);
	return ss.str();
}


void register_Function(pybind11::module_ & m) {
	py::class_<llvm::Function, std::unique_ptr<llvm::Function, py::nodelete>> Function(m, "Function");
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
			 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::Argument, std::unique_ptr<llvm::Argument, py::nodelete>, llvm::Value>(m, "Argument")
		.def("setName", &llvm::Argument::setName)
		.def("getName", &llvm::Argument::getName)
		.def("getType", &llvm::Argument::getType);

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

void register_VectorOfTypePtr(pybind11::module_ & m) {
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
}

void register_Types(pybind11::module_ & m) {
	// owned by context => no delete
	py::class_<llvm::Type, std::unique_ptr<llvm::Type, py::nodelete>>(m, "Type")
			.def("getVoidTy", &llvm::Type::getVoidTy, py::return_value_policy::reference)
			.def("getIntNTy", &llvm::Type::getIntNTy, py::return_value_policy::reference)
			.def("getIntNPtrTy", &llvm::Type::getIntNPtrTy, py::return_value_policy::reference);

	py::class_<llvm::PointerType, std::unique_ptr<llvm::PointerType, py::nodelete>, llvm::Type>(m, "PointerType")
			.def("getPointerElementType", &llvm::PointerType::getPointerElementType, py::return_value_policy::reference);
	m.def("TypeToPointerType", [](llvm::Type & t) {
				if (t.isPointerTy())
					return (llvm::PointerType*) &t;
				else
					return (llvm::PointerType*) nullptr;
			}, py::return_value_policy::reference)
		.def("TypeToIntegerType",[](llvm::Type & t) {
				if (t.isIntegerTy())
					return (llvm::IntegerType*) &t;
				else
					return (llvm::IntegerType*) nullptr;
			}, py::return_value_policy::reference);

	py::class_<llvm::FunctionType, std::unique_ptr<llvm::FunctionType, py::nodelete>>(m, "FunctionType")
		.def("get", [](llvm::Type *Result, const std::vector<llvm::Type*> &Params,
				bool isVarArg) {
			return llvm::FunctionType::get(Result, Params, isVarArg);
		}, py::return_value_policy::reference);
	py::class_<llvm::IntegerType, llvm::Type>(m, "IntegerType")
			.def("getBitWidth", &llvm::IntegerType::getBitWidth)
			.def("__repr__",  &printToStr<llvm::IntegerType>);
	py::implicitly_convertible<llvm::IntegerType, llvm::Type>();
}

void register_Attribute_and_MDNode(pybind11::module_ & m) {
	//llvm::AttributeSet
	//py::class_<llvm::Attribute, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
	py::class_<llvm::Metadata, std::unique_ptr<llvm::Metadata, py::nodelete>>(m, "Metadata");
	py::class_<llvm::MDString, llvm::Metadata>(m, "MDString")
		.def("get", [](llvm::LLVMContext &Context, llvm::StringRef Str) {
			llvm::MDString::get(Context, Str);
		}, py::return_value_policy::reference);
}

// https://github.com/PointCloudLibrary/clang-bind
// http://nondot.org/~sabre/LLVMNotes/TypeSystemChanges.txt
PYBIND11_MODULE(llvmIr, m) {
	genericFpgaTargetInitialize();
	py::class_<hwtHls::LlvmCompilationBundle>(m, "LlvmCompilationBundle")
		.def(py::init<const std::string &>())
		.def("runOpt", [](hwtHls::LlvmCompilationBundle * LCB, const py::object & o) {
			// :note: lambda specified explicitly so we can modify reference handling
			LCB->runOpt([o](llvm::MachineFunction &MF,
					std::set<hwtHls::GenericFpgaToNetlist::MachineBasicBlockEdge>& backedges,
					hwtHls::EdgeLivenessDict & liveness,
					std::vector<llvm::Register> & ioRegs,
					std::map<llvm::Register, unsigned> & registerTypes,
					llvm::MachineLoopInfo & loops) {
				o.operator() <py::return_value_policy::reference, llvm::MachineFunction &>(
						MF, backedges, liveness, ioRegs, registerTypes, loops
				);
			});
		})
		.def("getMachineFunction", &hwtHls::LlvmCompilationBundle::getMachineFunction)
		.def_readonly("ctx", &hwtHls::LlvmCompilationBundle::ctx)
		.def_readonly("strCtx", &hwtHls::LlvmCompilationBundle::strCtx)
		.def_readonly("mod", &hwtHls::LlvmCompilationBundle::mod)
		.def_readonly("builder", &hwtHls::LlvmCompilationBundle::builder)
		.def_readwrite("main", &hwtHls::LlvmCompilationBundle::main);

	py::class_<llvm::LLVMContext,  std::unique_ptr<llvm::LLVMContext, py::nodelete>>(m, "LLVMContext"); // construct using LlvmCompilationBundle
	py::class_<llvm::Module>(m, "Module")
			.def(py::init<llvm::StringRef, llvm::LLVMContext&>(), py::keep_alive<1, 2>(), py::keep_alive<1, 3>())
			.def("__repr__", &Module__repr__)
			.def("getName", &llvm::Module::getName);
	register_VectorOfTypePtr(m);
	register_IRBuilder(m);
	register_strings(m);
	register_Values_and_Use(m);

	py::class_<llvm::BasicBlock, std::unique_ptr<llvm::BasicBlock, py::nodelete>, llvm::Value>(m, "BasicBlock")
		.def("Create", &llvm::BasicBlock::Create, py::return_value_policy::reference)
		.def("getName", &llvm::BasicBlock::getName)
		.def("__iter__", [](llvm::BasicBlock &F) {
				return py::make_iterator(F.begin(), F.end());
			}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	register_Function(m);
	register_Types(m);
	register_Instruction(m);
	register_Attribute_and_MDNode(m);

	m.def("errs", &llvm::errs);

	py::class_<llvm::FunctionPass>(m, "FunctionPass");

	m.def("verifyFunction", [](const llvm::Function &F) {
		auto & e = llvm::errs();
		return llvm::verifyFunction(F, &e);
	});
	m.def("verifyModule", [](const llvm::Module &M) {
		auto & e = llvm::errs();
		return llvm::verifyModule(M, &e);
	});
	register_MachineFunction(m);
}

