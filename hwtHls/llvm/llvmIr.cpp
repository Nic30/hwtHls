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

#include "llvmPasses.h"

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

void register_IRBuilder(pybind11::module_ & m) {
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
		.def("CreateNeg", &llvm::IRBuilder<>::CreateNeg)
		.def("CreateAdd", &llvm::IRBuilder<>::CreateAdd, py::return_value_policy::reference)
		.def("CreateSub", &llvm::IRBuilder<>::CreateSub, py::return_value_policy::reference)
		.def("CreateMul", &llvm::IRBuilder<>::CreateMul, py::return_value_policy::reference)
		.def("CreateLShr", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool isExact=false) {
			return self->CreateLShr(LHS, RHS, Name, isExact);
		 })
		.def("CreateShl", [](llvm::IRBuilder<> * self, llvm::Value *LHS, llvm::Value *RHS,
				const llvm::Twine &Name = "", bool HasNUW = false, bool HasNSW = false) {
			return self->CreateShl(LHS, RHS, Name, HasNUW, HasNSW);
		})
		.def("CreateRetVoid", &llvm::IRBuilder<>::CreateRetVoid)
		.def("CreateStore", &llvm::IRBuilder<>::CreateStore, py::return_value_policy::reference)
		.def("CreateLoad", [](llvm::IRBuilder<> * self, llvm::Type *Ty, llvm::Value *Ptr, bool isVolatile,
                const llvm::Twine &Name = "") {
				return self->CreateLoad(Ty, Ptr, isVolatile, Name);
			}, py::return_value_policy::reference)
		.def("SetInsertPoint", [](llvm::IRBuilder<> * self, llvm::BasicBlock * bb) {
			self->SetInsertPoint(bb);
		})
		.def("CreateZExt", &llvm::IRBuilder<>::CreateZExt, py::return_value_policy::reference)
		.def("CreateSExt", &llvm::IRBuilder<>::CreateSExt, py::return_value_policy::reference)
		.def("CreateTrunc", &llvm::IRBuilder<>::CreateTrunc, py::return_value_policy::reference)
		.def("CreatePHI", &llvm::IRBuilder<>::CreatePHI, py::return_value_policy::reference)
		.def("CreateICmpEQ", &llvm::IRBuilder<>::CreateICmpEQ, py::return_value_policy::reference)
		.def("CreateICmpNE", &llvm::IRBuilder<>::CreateICmpNE, py::return_value_policy::reference)
		.def("CreateICmpSGE", &llvm::IRBuilder<>::CreateICmpSGE, py::return_value_policy::reference)
		.def("CreateICmpUGE", &llvm::IRBuilder<>::CreateICmpUGE, py::return_value_policy::reference)
		.def("CreateICmpSGT", &llvm::IRBuilder<>::CreateICmpSGT, py::return_value_policy::reference)
		.def("CreateICmpUGT", &llvm::IRBuilder<>::CreateICmpUGT, py::return_value_policy::reference)
		.def("CreateICmpSLE", &llvm::IRBuilder<>::CreateICmpSLE, py::return_value_policy::reference)
		.def("CreateICmpULE", &llvm::IRBuilder<>::CreateICmpULE, py::return_value_policy::reference)
		.def("CreateICmpSLT", &llvm::IRBuilder<>::CreateICmpSLT, py::return_value_policy::reference)
		.def("CreateICmpULT", &llvm::IRBuilder<>::CreateICmpULT, py::return_value_policy::reference)
		.def("CreateBr", &llvm::IRBuilder<>::CreateBr, py::return_value_policy::reference)
		.def("CreateCondBr", [](llvm::IRBuilder<> * self, llvm::Value *Cond, llvm::BasicBlock *True, llvm::BasicBlock *False,
				llvm::Instruction *MDSrc) {
				self->CreateCondBr(Cond, True, False, MDSrc);
			}, py::return_value_policy::reference)
		.def("CreateSwitch", &llvm::IRBuilder<>::CreateSwitch, py::return_value_policy::reference)
				;
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

void register_strings(pybind11::module_ & m) {
	py::class_<llvm::StringRef>(m, "StringRef")
		.def("__repr__", &StringRef__repr__)
		.def("str", & llvm::StringRef::str);
	py::class_<llvm::Twine>(m, "Twine")
		.def("__repr__", &Twine__repr__)
		.def("str", & llvm::Twine::str);
	py::class_<LLVMStringContext>(m, "LLVMStringContext")
		.def(py::init<>())
		.def("addStringRef", &LLVMStringContext::addStringRef, py::return_value_policy::reference)
		.def("addTwine", &LLVMStringContext::addTwine, py::return_value_policy::reference);
}

void register_Instruction(pybind11::module_ & m) {
	py::class_<llvm::Instruction, std::unique_ptr<llvm::Instruction, py::nodelete>, llvm::User> Instruction(m, "Instruction");
	Instruction
		.def("getOpcode", &llvm::Instruction::getOpcode)
		.def("getOpcodeName", [](llvm::Instruction*self) {
				return self->getOpcodeName();
			}, py::return_value_policy::reference);
	m.def("ValueToInstruction", [](llvm::Value* V) {
		  if (llvm::Instruction *Inst = llvm::dyn_cast<llvm::Instruction>(V)) {
		    return Inst;
		  } else {
			  return (llvm::Instruction *) nullptr;
		  }
	});

	py::enum_<llvm::Instruction::TermOps>(Instruction, "TermOps")
		.value("Ret", llvm::Instruction::TermOps::Ret)
		.value("Br", llvm::Instruction::TermOps::Br)
		.value("Switch", llvm::Instruction::TermOps::Switch)
		.value("IndirectBr", llvm::Instruction::TermOps::IndirectBr)
		.value("Invoke", llvm::Instruction::TermOps::Invoke)
		.value("Resume", llvm::Instruction::TermOps::Resume)
		.value("Unreachable", llvm::Instruction::TermOps::Unreachable)
		.value("CleanupRet", llvm::Instruction::TermOps::CleanupRet)
		.value("CatchRet", llvm::Instruction::TermOps::CatchRet)
		.value("CatchSwitch", llvm::Instruction::TermOps::CatchSwitch)
		.value("CallBr", llvm::Instruction::TermOps::CallBr)
		.export_values();

	py::enum_<llvm::Instruction::UnaryOps>(Instruction, "UnaryOps")
		.value("FNeg", llvm::Instruction::UnaryOps::FNeg)
		.export_values();

	py::enum_<llvm::Instruction::BinaryOps>(Instruction, "BinaryOps")
		.value("Add", llvm::Instruction::BinaryOps::Add)
		.value("FAdd", llvm::Instruction::BinaryOps::FAdd)
		.value("Sub", llvm::Instruction::BinaryOps::Sub)
		.value("FSub", llvm::Instruction::BinaryOps::FSub)
		.value("Mul", llvm::Instruction::BinaryOps::Mul)
		.value("FMul", llvm::Instruction::BinaryOps::FMul)
		.value("UDiv", llvm::Instruction::BinaryOps::UDiv)
		.value("SDiv", llvm::Instruction::BinaryOps::SDiv)
		.value("FDiv", llvm::Instruction::BinaryOps::FDiv)
		.value("URem", llvm::Instruction::BinaryOps::URem)
		.value("SRem", llvm::Instruction::BinaryOps::SRem)
		.value("FRem", llvm::Instruction::BinaryOps::FRem)
		.value("Shl", llvm::Instruction::BinaryOps::Shl)
		.value("LShr", llvm::Instruction::BinaryOps::LShr)
		.value("AShr", llvm::Instruction::BinaryOps::AShr)
		.value("And", llvm::Instruction::BinaryOps::And)
		.value("Or", llvm::Instruction::BinaryOps::Or)
		.value("Xor", llvm::Instruction::BinaryOps::Xor)
		.export_values();

	py::enum_<llvm::Instruction::MemoryOps>(Instruction, "MemoryOps")
		.value("Alloca", llvm::Instruction::MemoryOps::Alloca)
		.value("Load", llvm::Instruction::MemoryOps::Load)
		.value("Store", llvm::Instruction::MemoryOps::Store)
		.value("GetElementPtr", llvm::Instruction::MemoryOps::GetElementPtr)
		.value("Fence", llvm::Instruction::MemoryOps::Fence)
		.value("AtomicCmpXchg", llvm::Instruction::MemoryOps::AtomicCmpXchg)
		.value("AtomicRMW", llvm::Instruction::MemoryOps::AtomicRMW)
		.export_values();

	py::enum_<llvm::Instruction::CastOps>(Instruction, "CastOps")
		.value("Trunc", llvm::Instruction::CastOps::Trunc)
		.value("ZExt", llvm::Instruction::CastOps::ZExt)
		.value("SExt", llvm::Instruction::CastOps::SExt)
		.value("FPToUI", llvm::Instruction::CastOps::FPToUI)
		.value("FPToSI", llvm::Instruction::CastOps::FPToSI)
		.value("UIToFP", llvm::Instruction::CastOps::UIToFP)
		.value("SIToFP", llvm::Instruction::CastOps::SIToFP)
		.value("FPTrunc", llvm::Instruction::CastOps::FPTrunc)
		.value("FPExt", llvm::Instruction::CastOps::FPExt)
		.value("PtrToInt", llvm::Instruction::CastOps::PtrToInt)
		.value("IntToPtr", llvm::Instruction::CastOps::IntToPtr)
		.value("BitCast", llvm::Instruction::CastOps::BitCast)
		.value("AddrSpaceCast", llvm::Instruction::CastOps::AddrSpaceCast)
		.export_values();

	py::enum_<llvm::Instruction::FuncletPadOps>(Instruction, "FuncletPadOps")
		.value("CleanupPad", llvm::Instruction::FuncletPadOps::CleanupPad)
		.value("CatchPad", llvm::Instruction::FuncletPadOps::CatchPad)
		.export_values();

	py::enum_<llvm::Instruction::OtherOps>(Instruction, "OtherOps")
		.value("ICmp", llvm::Instruction::OtherOps::ICmp)
		.value("FCmp", llvm::Instruction::OtherOps::FCmp)
		.value("PHI", llvm::Instruction::OtherOps::PHI)
		.value("Call", llvm::Instruction::OtherOps::Call)
		.value("Select", llvm::Instruction::OtherOps::Select)
		.value("UserOp1", llvm::Instruction::OtherOps::UserOp1)
		.value("UserOp2", llvm::Instruction::OtherOps::UserOp2)
		.value("VAArg", llvm::Instruction::OtherOps::VAArg)
		.value("ExtractElement", llvm::Instruction::OtherOps::ExtractElement)
		.value("InsertElement", llvm::Instruction::OtherOps::InsertElement)
		.value("ShuffleVector", llvm::Instruction::OtherOps::ShuffleVector)
		.value("ExtractValue", llvm::Instruction::OtherOps::ExtractValue)
		.value("InsertValue", llvm::Instruction::OtherOps::InsertValue)
		.value("LandingPad", llvm::Instruction::OtherOps::LandingPad)
		.value("Freeze", llvm::Instruction::OtherOps::Freeze)
		.export_values();

	py::class_<llvm::CmpInst, std::unique_ptr<llvm::CmpInst, py::nodelete>, llvm::Instruction> CmpInstr(m, "CmpInst");
	py::enum_<llvm::CmpInst::Predicate>(CmpInstr, "Predicate")
	    .value("FCMP_FALSE", llvm::CmpInst::Predicate::FCMP_FALSE)
	    .value("FCMP_OEQ", llvm::CmpInst::Predicate::FCMP_OEQ)
	    .value("FCMP_OGT", llvm::CmpInst::Predicate::FCMP_OGT)
	    .value("FCMP_OGE", llvm::CmpInst::Predicate::FCMP_OGE)
	    .value("FCMP_OLT", llvm::CmpInst::Predicate::FCMP_OLT)
	    .value("FCMP_OLE", llvm::CmpInst::Predicate::FCMP_OLE)
	    .value("FCMP_ONE", llvm::CmpInst::Predicate::FCMP_ONE)
	    .value("FCMP_ORD", llvm::CmpInst::Predicate::FCMP_ORD)
	    .value("FCMP_UNO", llvm::CmpInst::Predicate::FCMP_UNO)
	    .value("FCMP_UEQ", llvm::CmpInst::Predicate::FCMP_UEQ)
	    .value("FCMP_UGT", llvm::CmpInst::Predicate::FCMP_UGT)
	    .value("FCMP_UGE", llvm::CmpInst::Predicate::FCMP_UGE)
	    .value("FCMP_ULT", llvm::CmpInst::Predicate::FCMP_ULT)
	    .value("FCMP_ULE", llvm::CmpInst::Predicate::FCMP_ULE)
	    .value("FCMP_UNE", llvm::CmpInst::Predicate::FCMP_UNE)
	    .value("FCMP_TRUE", llvm::CmpInst::Predicate::FCMP_TRUE)
	    .value("FIRST_FCMP_PREDICATE", llvm::CmpInst::Predicate::FIRST_FCMP_PREDICATE)
	    .value("LAST_FCMP_PREDICATE", llvm::CmpInst::Predicate::LAST_FCMP_PREDICATE)
	    .value("BAD_FCMP_PREDICATE", llvm::CmpInst::Predicate::BAD_FCMP_PREDICATE)
	    .value("ICMP_EQ", llvm::CmpInst::Predicate::ICMP_EQ)
	    .value("ICMP_NE", llvm::CmpInst::Predicate::ICMP_NE)
	    .value("ICMP_UGT", llvm::CmpInst::Predicate::ICMP_UGT)
	    .value("ICMP_UGE", llvm::CmpInst::Predicate::ICMP_UGE)
	    .value("ICMP_ULT", llvm::CmpInst::Predicate::ICMP_ULT)
	    .value("ICMP_ULE", llvm::CmpInst::Predicate::ICMP_ULE)
	    .value("ICMP_SGT", llvm::CmpInst::Predicate::ICMP_SGT)
	    .value("ICMP_SGE", llvm::CmpInst::Predicate::ICMP_SGE)
	    .value("ICMP_SLT", llvm::CmpInst::Predicate::ICMP_SLT)
	    .value("ICMP_SLE", llvm::CmpInst::Predicate::ICMP_SLE)
	    .value("FIRST_ICMP_PREDICATE", llvm::CmpInst::Predicate::FIRST_ICMP_PREDICATE)
	    .value("LAST_ICMP_PREDICATE", llvm::CmpInst::Predicate::LAST_ICMP_PREDICATE)
	    .value("BAD_ICMP_PREDICATE", llvm::CmpInst::Predicate::BAD_ICMP_PREDICATE)
		.export_values();
	CmpInstr
		.def("getPredicate", &llvm::CmpInst::getPredicate);

	py::class_<llvm::ICmpInst, std::unique_ptr<llvm::ICmpInst, py::nodelete>, llvm::CmpInst>(m, "ICmpInst");
	m.def("InstructionToICmpInst", [](llvm::Instruction * I) {
		if (llvm::ICmpInst *Inst = llvm::dyn_cast<llvm::ICmpInst>(I)) {
		  return Inst;
		} else {
		  return (llvm::ICmpInst *) nullptr;
		}
	});

	py::class_<llvm::UnaryInstruction, std::unique_ptr<llvm::UnaryInstruction, py::nodelete>, llvm::Instruction>(m, "UnaryInstruction");
	py::class_<llvm::LoadInst, std::unique_ptr<llvm::LoadInst, py::nodelete>, llvm::UnaryInstruction>(m, "LoadInst")
		.def("isVolatile", &llvm::LoadInst::isVolatile);
	py::class_<llvm::StoreInst, std::unique_ptr<llvm::StoreInst, py::nodelete>, llvm::Instruction>(m, "StoreInst");
	py::class_<llvm::ReturnInst, std::unique_ptr<llvm::ReturnInst, py::nodelete>, llvm::Instruction>(m, "ReturnInst");
	py::class_<llvm::BranchInst, std::unique_ptr<llvm::BranchInst, py::nodelete>, llvm::Instruction>(m, "BranchInst");
	py::class_<llvm::SwitchInst, std::unique_ptr<llvm::SwitchInst, py::nodelete>, llvm::Instruction>(m, "SwitchInst")
			.def("addCase", &llvm::SwitchInst::addCase);

	py::class_<llvm::PHINode,  std::unique_ptr<llvm::PHINode, py::nodelete>, llvm::Instruction>(m, "PHINode")
		.def("addIncoming", &llvm::PHINode::addIncoming)
		.def("iterBlocks", [](llvm::PHINode &p) {
			 	return py::make_iterator(p.block_begin(), p.block_end());
			 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */
	m.def("InstructionToPHINode", [](llvm::Instruction * I) {
		if (llvm::PHINode *Inst = llvm::dyn_cast<llvm::PHINode>(I)) {
		  return Inst;
		} else {
		  return (llvm::PHINode *) nullptr;
		}
	});
}


void register_Types(pybind11::module_ & m) {
	// owned by context => no delete
	py::class_<llvm::Type, std::unique_ptr<llvm::Type, py::nodelete>>(m, "Type")
			.def("getVoidTy", &llvm::Type::getVoidTy, py::return_value_policy::reference)
			.def("getIntNTy", &llvm::Type::getIntNTy, py::return_value_policy::reference)
			.def("getIntNPtrTy", &llvm::Type::getIntNPtrTy, py::return_value_policy::reference);

	py::class_<llvm::PointerType, std::unique_ptr<llvm::PointerType, py::nodelete>, llvm::Type>(m, "PointerType")
			.def("getElementType", &llvm::PointerType::getElementType, py::return_value_policy::reference);
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
namespace pybind11 __attribute__((visibility("hidden"))) {
class int_fromStr : public py::int_ {
public:
	int_fromStr(const std::string & str) {
		m_ptr = PyLong_FromString(str.c_str(), nullptr, 16);
	}

};
}
// https://github.com/PointCloudLibrary/clang-bind
// http://nondot.org/~sabre/LLVMNotes/TypeSystemChanges.txt
PYBIND11_MODULE(toLlvm, m) {

   //AttributeSet
   //Attribute
	py::class_<llvm::LLVMContext>(m, "LLVMContext")
			.def(py::init<>());
	py::class_<llvm::Module>(m, "Module")
			.def(py::init<llvm::StringRef, llvm::LLVMContext&>(), py::keep_alive<1, 2>(), py::keep_alive<1, 3>())
			.def("__repr__", &Module__repr__);
	register_VectorOfTypePtr(m);
	register_IRBuilder(m);
	py::class_<llvm::Value, std::unique_ptr<llvm::Value, py::nodelete>>(m, "Value")
			.def("__repr__", &printToStr<llvm::Value>)
			.def("__hash__", [](llvm::Value * v) {
				return reinterpret_cast<intptr_t>(v);
			})
			.def("__eq__", [](llvm::Value * v0, llvm::Value * v1){
				return v0 == v1;
			})
			.def("getType", &llvm::Value::getType, py::return_value_policy::reference)
			.def("getName", &llvm::Value::getName)
			.def("users", [](llvm::Value &v) {
				auto users = v.users();
			 	return py::make_iterator(users.begin(), users.end());
			 }, py::keep_alive<0, 1>());

	register_strings(m);

	py::class_<llvm::BasicBlock, std::unique_ptr<llvm::BasicBlock, py::nodelete>, llvm::Value>(m, "BasicBlock")
		.def("Create", &llvm::BasicBlock::Create, py::return_value_policy::reference)
		.def("getName", &llvm::BasicBlock::getName)
		.def("__iter__", [](llvm::BasicBlock &F) {
				return py::make_iterator(F.begin(), F.end());
			}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */


	register_Function(m);
	register_Types(m);

	// owned by context => no delete
	py::class_<llvm::User, std::unique_ptr<llvm::User, py::nodelete>, llvm::Value>(m, "User")
		.def("iterOperands", [](llvm::User &v) {
			 	return py::make_iterator(v.op_begin(), v.op_end());
			 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */;
	m.def("UserToInstruction", [](llvm::User * U) {
		  if (llvm::Instruction *Inst = llvm::dyn_cast<llvm::Instruction>(U)) {
		    return Inst;
		  } else {
			  return (llvm::Instruction *) nullptr;
		  }
	});
	py::class_<llvm::Use, std::unique_ptr<llvm::Use, py::nodelete>>(m, "Use")
		.def("get", &llvm::Use::get);

	register_Instruction(m);


	m.def("errs", &llvm::errs);

	py::class_<llvm::APInt>(m, "APInt")
		.def(py::init<unsigned, llvm::StringRef, uint8_t>())
		.def_static("getAllOnesValue", llvm::APInt::getAllOnesValue)
		.def_static("getBitsSet", llvm::APInt::getBitsSet)
		.def("__int__", [](llvm::APInt* I) {
			auto str = I->toString(16, false);
			return pybind11::int_fromStr(str.c_str());
		});
	py::class_<llvm::Constant, std::unique_ptr<llvm::Constant, py::nodelete>, llvm::User>(m, "Constant");
	py::class_<llvm::ConstantData, std::unique_ptr<llvm::ConstantData, py::nodelete>, llvm::Constant>(m, "ConstantData");
	py::class_<llvm::ConstantInt, std::unique_ptr<llvm::ConstantInt, py::nodelete>, llvm::ConstantData>(m, "ConstantInt")
		.def_static("get", [](llvm::Type* Ty, llvm::APInt& V) {
			return llvm::ConstantInt::get(Ty, V);
		}, py::return_value_policy::reference)
		.def("getValue", &llvm::ConstantInt::getValue);
	m.def("ValueToConstantInt", [](llvm::Value * V) {
		  if (llvm::ConstantInt *CI = llvm::dyn_cast<llvm::ConstantInt>(V)) {
		    return CI;
		  } else {
			  return (llvm::ConstantInt *) nullptr;
		  }
	});


	py::class_<llvm::FunctionPass>(m, "FunctionPass");
	m.def("runOpt", &runOpt);
	m.def("verifyFunction", [](const llvm::Function &F) {
		auto & e = llvm::errs();
		return llvm::verifyFunction(F, &e);
	});
	m.def("verifyModule", [](const llvm::Module &M) {
		auto & e = llvm::errs();
		return llvm::verifyModule(M, &e);
	});

}

