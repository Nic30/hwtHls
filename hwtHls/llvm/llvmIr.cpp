#include "llvmIrCommon.h"
#include "llvmIrBuilder.h"
#include "llvmIrFunction.h"
#include "llvmIrInstruction.h"
#include "llvmIrStrings.h"
#include "llvmIrValues.h"
#include "llvmIrMachineFunction.h"
#include "llvmIrMachineLoop.h"
#include "llvmIrMetadata.h"
#include "llvmCompilationBundle.h"
#include "targets/hwtFpga.h"
#include "targets/Transforms/hwtFpgaToNetlist.h"

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/CodeGen/MachineInstr.h>


#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;
PYBIND11_MAKE_OPAQUE(std::vector<llvm::Type*>);

namespace hwtHls {

// https://pybind11.readthedocs.io/en/stable/advanced/classes.html
// https://github.com/llvm/circt/blob/main/lib/Bindings/Python/MSFTModule.cpp
// https://blog.ekbana.com/write-a-python-binding-for-your-c-code-using-pybind11-library-ef0992d4b68


std::string Module__repr__(llvm::Module *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss, nullptr);
	return ss.str();
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
		.def("getIntegerBitWidth", &llvm::Type::getIntegerBitWidth, py::return_value_policy::reference)
		.def("getIntNPtrTy", &llvm::Type::getIntNPtrTy, py::return_value_policy::reference)
		.def("__repr__",  &printToStr<llvm::Type>);;

	py::class_<llvm::PointerType, std::unique_ptr<llvm::PointerType, py::nodelete>, llvm::Type>(m, "PointerType")
		.def("get", [](llvm::LLVMContext &C, unsigned AddressSpace) {
			return llvm::PointerType::get(C, AddressSpace);
		},  py::return_value_policy::reference)
		.def("__repr__",  &printToStr<llvm::PointerType>);
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
	py::class_<llvm::ArrayType, std::unique_ptr<llvm::ArrayType, py::nodelete>, llvm::Type>(m, "ArrayType")
			.def("get", &llvm::ArrayType::get)
			.def("getElementType", &llvm::ArrayType::getElementType, py::return_value_policy::reference)
			.def("getNumElements", &llvm::ArrayType::getNumElements)
			.def("__repr__",  &printToStr<llvm::ArrayType>);
	m.def("TypeToArrayType", [](llvm::Type & t) {
				if (t.isArrayTy())
					return (llvm::ArrayType*) &t;
				else
					return (llvm::ArrayType*) nullptr;
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

// https://github.com/PointCloudLibrary/clang-bind
// http://nondot.org/~sabre/LLVMNotes/TypeSystemChanges.txt
PYBIND11_MODULE(llvmIr, m) {
	hwtFpgaTargetInitialize();
	py::class_<hwtHls::LlvmCompilationBundle>(m, "LlvmCompilationBundle")
		.def(py::init<const std::string &>())
		.def("runOpt", [](hwtHls::LlvmCompilationBundle * LCB, py::function & callbackFn, py::object & hls, py::object & toSsa) {
			py::object returnObj;
			LCB->runOpt([callbackFn, &hls, &toSsa, &returnObj](llvm::MachineFunction &MF,
					std::set<hwtHls::HwtFpgaToNetlist::MachineBasicBlockEdge>& backedges,
					hwtHls::EdgeLivenessDict & liveness,
					std::vector<llvm::Register> & ioRegs,
					std::map<llvm::Register, unsigned> & registerTypes,
					llvm::MachineLoopInfo & loops) {
				// :note: specified explicitly so we can modify reference handling and pass python objects without
				//        spoiling C++ llvm code with pybind11
				returnObj = callbackFn.operator() <py::return_value_policy::reference,
						py::object &,
						py::object &,
						llvm::MachineFunction &,
						std::set<hwtHls::HwtFpgaToNetlist::MachineBasicBlockEdge>&,
					    hwtHls::EdgeLivenessDict &,
					    std::vector<llvm::Register> &,
					    std::map<llvm::Register, unsigned> &,
					    llvm::MachineLoopInfo &>(
					    		hls, toSsa,MF, backedges, liveness, ioRegs, registerTypes, loops
				);
			});
			return returnObj;
		})
		.def("getMachineFunction", &hwtHls::LlvmCompilationBundle::getMachineFunction, py::return_value_policy::reference_internal)
		.def("getMachineModuleInfo", &hwtHls::LlvmCompilationBundle::getMachineModuleInfo, py::return_value_policy::reference_internal)
		.def("_testSlicesToIndependentVariablesPass", &hwtHls::LlvmCompilationBundle::_testSlicesToIndependentVariablesPass, py::return_value_policy::reference_internal)
		.def("_testSlicesMergePass", &hwtHls::LlvmCompilationBundle::_testSlicesMergePass, py::return_value_policy::reference_internal)
		.def_readonly("ctx", &hwtHls::LlvmCompilationBundle::ctx)
		.def_readonly("strCtx", &hwtHls::LlvmCompilationBundle::strCtx)
		.def_readonly("mod", &hwtHls::LlvmCompilationBundle::mod)
		.def_readonly("builder", &hwtHls::LlvmCompilationBundle::builder)
		.def_readwrite("main", &hwtHls::LlvmCompilationBundle::main);

	py::class_<llvm::LLVMContext,  std::unique_ptr<llvm::LLVMContext, py::nodelete>>(m, "LLVMContext"); // construct using LlvmCompilationBundle
	py::class_<llvm::Module, std::unique_ptr<llvm::Module, py::nodelete>>(m, "Module")
			.def(py::init<llvm::StringRef, llvm::LLVMContext&>(), py::keep_alive<1, 2>(), py::keep_alive<1, 3>())
			.def("__repr__", &Module__repr__)
			.def("getName", &llvm::Module::getName)
			.def("getFunction", &llvm::Module::getFunction)
			.def("__iter__", [](llvm::Module &M) {
					return py::make_iterator(M.begin(), M.end());
				}, py::keep_alive<0, 1>());
	register_VectorOfTypePtr(m);
	register_IRBuilder(m);
	register_strings(m);
	register_Values_and_Use(m);

	py::class_<llvm::BasicBlock, std::unique_ptr<llvm::BasicBlock, py::nodelete>, llvm::Value>(m, "BasicBlock")
		.def("Create", &llvm::BasicBlock::Create, py::return_value_policy::reference_internal)
		.def("getName", &llvm::BasicBlock::getName)
		.def("__iter__", [](llvm::BasicBlock &F) {
				return py::make_iterator(F.begin(), F.end());
			}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	register_Function(m);
	register_Types(m);
	register_Attribute(m);
	register_MDNode(m);
	register_Instruction(m);

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
	register_MachineLoop(m);

	py::class_<llvm::SMDiagnostic> (m, "SMDiagnostic")
			.def(py::init<>())
			.def("str", [](llvm::SMDiagnostic * self, const char *ProgName, bool ShowColors, bool ShowKindLabel) {
					std::string tmp;
					llvm::raw_string_ostream ss(tmp);
					self->print(ProgName, ss, ShowColors, ShowKindLabel);
					return ss.str();
				}
				// py::arg_v("ShowColors", true, "ShowColors=True"),
				// py::arg_v("ShowKindLabel", true, "ShowKindLabel=True")
				);
	m.def("parseIR", [](const std::string & str, const std::string & name, llvm::SMDiagnostic &Err, llvm::LLVMContext &Context) {
		llvm::MemoryBufferRef buff(str, name);
		return llvm::parseIR(buff, Err, Context);
	}, py::return_value_policy::reference_internal);

}
}
