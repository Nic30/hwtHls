#include "llvmIrInstruction.h"

#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>

#include "llvmIrMetadata.h"


namespace py = pybind11;

namespace hwtHls {

template<typename T>
T* llvmInstructionCaster(llvm::Instruction *I) {
	if (T *Inst = llvm::dyn_cast<T>(I)) {
		return Inst;
	} else {
		return (T*) nullptr;
	}
}

void register_Instruction(pybind11::module_ & m) {
	py::class_<llvm::Instruction, std::unique_ptr<llvm::Instruction, py::nodelete>, llvm::User> Instruction(m, "Instruction");
	Instruction
		.def("getOpcode", &llvm::Instruction::getOpcode)
		.def("getOpcodeName", [](llvm::Instruction*self) {
				return self->getOpcodeName();
			}, py::return_value_policy::reference)
		.def("__eq__", [](const llvm::Instruction & self, const llvm::Instruction & other) {
			return &self == &other;
		})
		.def("__eq__", [](const llvm::Instruction & self, const llvm::Value & other) {
					return &self == &other;
		})
		.def("__hash__", [](const llvm::Instruction * self) {
			return reinterpret_cast<intptr_t>(self);
		})
		.def("getMetadata", [](llvm::Instruction * I, llvm::StringRef Kind) {
			return reinterpret_cast<MDNodeWithDeletedDelete*>(I->getMetadata(Kind));
		})
		.def("setMetadata", [](llvm::Instruction * I, llvm::StringRef Kind, MDNodeWithDeletedDelete *Node) {
			I->setMetadata(Kind, Node);
		})
		.def("getNextNode", [](llvm::Instruction * I) {
			return I->getNextNode();
		}, py::return_value_policy::reference_internal)
		.def("printAsOperand", [](const llvm::Instruction & I) {
			std::string tmp;
			llvm::raw_string_ostream ss(tmp);
			I.printAsOperand(ss, true,  I.getParent()->getParent() ? I.getParent()->getParent()->getParent() : nullptr);
			return ss.str();
		});
	m.def("ValueToInstruction", [](llvm::Value* V) {
		  if (llvm::Instruction *Inst = llvm::dyn_cast<llvm::Instruction>(V)) {
		     return Inst;
		  } else {
			  return (llvm::Instruction *) nullptr;
		  }
	}, py::return_value_policy::reference_internal);
	m.def("UserToInstruction", [](llvm::User * U) {
		  if (llvm::Instruction *Inst = llvm::dyn_cast<llvm::Instruction>(U)) {
		     return Inst;
		  } else {
			  return (llvm::Instruction *) nullptr;
		  }
	}, py::return_value_policy::reference_internal);
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

	py::class_<llvm::BinaryOperator, std::unique_ptr<llvm::BinaryOperator, py::nodelete>, llvm::Instruction>(m, "BinaryOperator");
	py::implicitly_convertible<llvm::BinaryOperator, llvm::Instruction>();
	m.def("InstructionToBinaryOperator", &llvmInstructionCaster<llvm::BinaryOperator>, py::return_value_policy::reference_internal);

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

	py::class_<llvm::CmpInst, std::unique_ptr<llvm::CmpInst, py::nodelete>, llvm::Instruction> CmpInst(m, "CmpInst");
	py::implicitly_convertible<llvm::CmpInst, llvm::Instruction>();
	py::enum_<llvm::CmpInst::Predicate>(CmpInst, "Predicate")
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
	CmpInst
		.def("getPredicate", &llvm::CmpInst::getPredicate);

	py::class_<llvm::ICmpInst, std::unique_ptr<llvm::ICmpInst, py::nodelete>, llvm::CmpInst>(m, "ICmpInst");
	py::implicitly_convertible<llvm::ICmpInst, llvm::Instruction>();
	m.def("InstructionToICmpInst", &llvmInstructionCaster<llvm::ICmpInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::CallBase, std::unique_ptr<llvm::CallBase, py::nodelete>, llvm::Instruction>(m, "CallBase");
	py::implicitly_convertible<llvm::CallBase, llvm::Instruction>();
	py::class_<llvm::CallInst, std::unique_ptr<llvm::CallInst, py::nodelete>, llvm::CallBase>(m, "CallInst");
	py::implicitly_convertible<llvm::CallInst, llvm::Instruction>();
	m.def("InstructionToCallInst", &llvmInstructionCaster<llvm::CallInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::UnaryInstruction, std::unique_ptr<llvm::UnaryInstruction, py::nodelete>, llvm::Instruction>(m, "UnaryInstruction");
	py::class_<llvm::LoadInst, std::unique_ptr<llvm::LoadInst, py::nodelete>, llvm::UnaryInstruction>(m, "LoadInst")
		.def("isVolatile", &llvm::LoadInst::isVolatile);
	py::implicitly_convertible<llvm::LoadInst, llvm::Instruction>();
	m.def("InstructionToLoadInst", &llvmInstructionCaster<llvm::LoadInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::StoreInst, std::unique_ptr<llvm::StoreInst, py::nodelete>, llvm::Instruction>(m, "StoreInst");
	py::implicitly_convertible<llvm::StoreInst, llvm::Instruction>();
	m.def("InstructionToStoreInst", &llvmInstructionCaster<llvm::StoreInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::ReturnInst, std::unique_ptr<llvm::ReturnInst, py::nodelete>, llvm::Instruction>(m, "ReturnInst");
	py::implicitly_convertible<llvm::ReturnInst, llvm::Instruction>();
	m.def("InstructionToReturnInst", &llvmInstructionCaster<llvm::ReturnInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::BranchInst, std::unique_ptr<llvm::BranchInst, py::nodelete>, llvm::Instruction>(m, "BranchInst");
	py::implicitly_convertible<llvm::BranchInst, llvm::Instruction>();
	m.def("InstructionToBranchInst", &llvmInstructionCaster<llvm::BranchInst>, py::return_value_policy::reference_internal);

	//llvm::Instruction::get
	//llvm::CallInst::addAttribute
	py::class_<llvm::SwitchInst, std::unique_ptr<llvm::SwitchInst, py::nodelete>, llvm::Instruction>(m, "SwitchInst")
			.def("addCase", &llvm::SwitchInst::addCase);
	py::implicitly_convertible<llvm::SwitchInst, llvm::Instruction>();
	m.def("InstructionToSwitchInst", &llvmInstructionCaster<llvm::SwitchInst>, py::return_value_policy::reference_internal);

	py::class_<llvm::PHINode,  std::unique_ptr<llvm::PHINode, py::nodelete>, llvm::Instruction>(m, "PHINode")
		.def("addIncoming", &llvm::PHINode::addIncoming)
		.def("getIncomingValueForBlock", &llvm::PHINode::getIncomingValueForBlock, py::return_value_policy::reference_internal)
		.def("iterBlocks", [](llvm::PHINode &p) {
			 	return py::make_iterator(p.block_begin(), p.block_end());
			 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */
	py::implicitly_convertible<llvm::PHINode, llvm::Instruction>();
	m.def("InstructionToPHINode", &llvmInstructionCaster<llvm::PHINode>, py::return_value_policy::reference_internal);
	py::class_<llvm::GetElementPtrInst,  std::unique_ptr<llvm::GetElementPtrInst, py::nodelete>, llvm::Instruction>(m, "GetElementPtrInst");
	py::implicitly_convertible<llvm::GetElementPtrInst, llvm::Instruction>();
	m.def("InstructionToGetElementPtrInst", &llvmInstructionCaster<llvm::GetElementPtrInst>, py::return_value_policy::reference_internal);

}
}
