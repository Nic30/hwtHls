#include <hwtHls/llvm/llvmIrCommon.h>
#include <hwtHls/llvm/llvmPyCompilationBundle.h>
#include <hwtHls/llvm/llvmIrAny.h>
#include <hwtHls/llvm/llvmIrLoop.h>
#include <hwtHls/llvm/llvmIrBuilder.h>
#include <hwtHls/llvm/llvmIrFunction.h>
#include <hwtHls/llvm/llvmIrGlobalVariable.h>
#include <hwtHls/llvm/llvmIrInstruction.h>
#include <hwtHls/llvm/llvmIrStrings.h>
#include <hwtHls/llvm/llvmIrValues.h>
#include <hwtHls/llvm/llvmIrMachineFunction.h>
#include <hwtHls/llvm/llvmIrMachineLoop.h>
#include <hwtHls/llvm/llvmIrMetadata.h>
#include <hwtHls/llvm/targets/hwtFpga.h>

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Pass.h>

#include <pybind11/pybind11.h>

#include <memory>
#include <string>
#include <vector>

namespace py = pybind11;
PYBIND11_MAKE_OPAQUE(std::vector<llvm::Type*>);

namespace hwtHls {

// https://pybind11.readthedocs.io/en/stable/advanced/classes.html
// https://github.com/llvm/circt/blob/main/lib/Bindings/Python/MSFTModule.cpp
// https://blog.ekbana.com/write-a-python-binding-for-your-c-code-using-pybind11-library-ef0992d4b68

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
		.def("getVoidTy", &llvm::Type::getVoidTy, py::return_value_policy::reference_internal)
		.def("getIntNTy", &llvm::Type::getIntNTy, py::return_value_policy::reference_internal)
		.def("getIntegerBitWidth", &llvm::Type::getIntegerBitWidth)
		.def("getPointerTo", &llvm::Type::getPointerTo, py::return_value_policy::reference)
		.def("__repr__",  &printToStr<llvm::Type>);;

	py::class_<llvm::PointerType, std::unique_ptr<llvm::PointerType, py::nodelete>, llvm::Type>(m, "PointerType")
		.def("get", [](llvm::LLVMContext &C, unsigned AddressSpace) {
			return llvm::PointerType::get(C, AddressSpace);
		},  py::return_value_policy::reference)
		.def("getAddressSpace", &llvm::PointerType::getAddressSpace)
		.def("__repr__",  &printToStr<llvm::PointerType>);
	py::implicitly_convertible<llvm::PointerType, llvm::Type>();
	m.def("TypeToPointerType", [](llvm::Type & t) {
			if (t.isPointerTy())
				return (llvm::PointerType*) &t;
			else
				return (llvm::PointerType*) nullptr;
		}, py::return_value_policy::reference);
	py::class_<llvm::ArrayType, std::unique_ptr<llvm::ArrayType, py::nodelete>, llvm::Type>(m, "ArrayType")
			.def("get", &llvm::ArrayType::get)
			.def("getElementType", &llvm::ArrayType::getElementType, py::return_value_policy::reference)
			.def("getNumElements", &llvm::ArrayType::getNumElements)
			.def("__repr__",  &printToStr<llvm::ArrayType>);
	py::implicitly_convertible<llvm::ArrayType, llvm::Type>();
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
	py::implicitly_convertible<llvm::FunctionType, llvm::Type>();

	py::class_<llvm::IntegerType, llvm::Type>(m, "IntegerType")
			.def("getBitWidth", &llvm::IntegerType::getBitWidth)
			.def("__repr__",  &printToStr<llvm::IntegerType>);
	py::implicitly_convertible<llvm::IntegerType, llvm::Type>();
	m.def("TypeToIntegerType",[](llvm::Type & t) {
 		if (t.isIntegerTy())
 			return (llvm::IntegerType*) &t;
 		else
 			return (llvm::IntegerType*) nullptr;
 	}, py::return_value_policy::reference);
}

void register_BasicBlock(pybind11::module_ & m) {
	py::class_<llvm::BasicBlock, std::unique_ptr<llvm::BasicBlock, py::nodelete>, llvm::Value>(m, "BasicBlock")
		.def("Create", &llvm::BasicBlock::Create, py::return_value_policy::reference_internal)
		.def("getName", &llvm::BasicBlock::getName)
		.def("getParent", [](llvm::BasicBlock & BB) {return BB.getParent();}, py::return_value_policy::reference_internal)
		.def("insertInto", &llvm::BasicBlock::insertInto)
		.def("printAsOperand", [](const llvm::BasicBlock & BB) {
			std::string tmp;
			llvm::raw_string_ostream ss(tmp);
			BB.printAsOperand(ss, true,  BB.getParent() ? BB.getParent()->getParent() : nullptr);
			return ss.str();
		})
		.def("__iter__", [](llvm::BasicBlock &BB) {
				return py::make_iterator(BB.begin(), BB.end());
			}, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
	    .def("__repr__", [](llvm::BasicBlock &BB) {
			return (std::string("<BasicBlock ") + BB.getName() + ">").str();
		});

	m.def("ValueToBasicBlock", [](llvm::Value *V) {
		if (llvm::BasicBlock *BB = llvm::dyn_cast<llvm::BasicBlock>(V)) {
			return BB;
		} else {
			return (llvm::BasicBlock*) nullptr;
		}
	});
}

std::string Module__repr__(llvm::Module *self) {
	std::string tmp;
	llvm::raw_string_ostream ss(tmp);
	self->print(ss, nullptr);
	return ss.str();
}

void register_Module(pybind11::module_ & m) {
	py::class_<llvm::Module, std::unique_ptr<llvm::Module, py::nodelete>>(m, "Module")
			.def(py::init<llvm::StringRef, llvm::LLVMContext&>(), py::keep_alive<1, 2>(), py::keep_alive<1, 3>())
			.def("__repr__", &Module__repr__)
			.def("getName", &llvm::Module::getName)
			.def("getFunction", &llvm::Module::getFunction)
			.def("__eq__", [](llvm::Module* self, llvm::Module* other) {
				return self == other;
			})
			.def("__hash__", [](llvm::Module * v) {
				return reinterpret_cast<intptr_t>(v);
			})
			.def("__iter__", [](llvm::Module &M) {
					return py::make_iterator(M.begin(), M.end());
				}, py::keep_alive<0, 1>());

}

// https://github.com/PointCloudLibrary/clang-bind
// http://nondot.org/~sabre/LLVMNotes/TypeSystemChanges.txt
PYBIND11_MODULE(llvmIr, m) {
	hwtFpgaTargetInitialize();
	// it is recommended to construct LLVMContext using LlvmCompilationBundle
	py::class_<llvm::LLVMContext, std::unique_ptr<llvm::LLVMContext, py::nodelete>>(m, "LLVMContext");
	register_Module(m);
	register_VectorOfTypePtr(m);
	register_strings(m);
	register_Values_and_Use(m);
	register_BasicBlock(m);
	register_Function(m);
	register_Types(m);
	register_Attribute(m);
	register_MDNode(m);
	register_Instruction(m);
	register_GlobalVariable(m);
	register_llvmAny(m);
	register_IRBuilder(m);
	register_Loop(m);
	register_MachineFunction(m);
	register_MachineLoop(m);
	register_LlvmCompilationBundle(m);

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
		auto M = llvm::parseIR(buff, Err, Context);
		return M.release();
	}, py::return_value_policy::reference_internal);

}
}
