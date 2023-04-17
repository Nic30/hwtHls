#include "llvmIrMachineFunction.h"
#include <sstream>
#include <pybind11/stl.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/MC/MCInstrInfo.h>

#include "llvmIrCommon.h"
#include "targets/genericFpgaMCTargetDesc.h"

namespace py = pybind11;

namespace hwtHls {

enum TargetOpcode: unsigned {};

void register_MachineFunction(pybind11::module_ &m) {
	py::class_<llvm::MachineFunction, std::unique_ptr<llvm::MachineFunction, py::nodelete>> MachineFunction(m, "MachineFunction");
	MachineFunction
		.def("getName", &llvm::MachineFunction::getName, py::return_value_policy::reference_internal)
		.def("getRegInfo", [](const llvm::MachineFunction * MF) {
			return &MF->getRegInfo();
		}, py::return_value_policy::reference_internal)
		.def("__repr__",  [](llvm::MachineFunction*MF) {
			return "<llvm::MachineFunction " + MF->getName().str() + ">";
		})
		.def("__str__",  &printToStr<llvm::MachineFunction>)
		.def("__iter__", [](llvm::MachineFunction &F) {
			return py::make_iterator(F.begin(), F.end());
		}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::MachineBasicBlock, std::unique_ptr<llvm::MachineBasicBlock, py::nodelete>> MachineBasicBlock(m, "MachineBasicBlock");
	MachineBasicBlock
		.def("getName", &llvm::MachineBasicBlock::getName, py::return_value_policy::reference_internal)
		.def("getNumber", &llvm::MachineBasicBlock::getNumber)
	    .def("predecessors", [](llvm::MachineBasicBlock &MB) {
	    		return py::make_iterator(MB.predecessors().begin(), MB.predecessors().end());
	    	}, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
	    .def("successors", [](llvm::MachineBasicBlock &MB) {
				auto succ = MB.successors();
	    	    return py::make_iterator(succ.begin(), succ.end());
	    	}, py::keep_alive<0, 1>()) /* Keep vector alive while iterator is used */
		.def("succ_size", &llvm::MachineBasicBlock::succ_size)
		.def("pred_size", &llvm::MachineBasicBlock::pred_size)
		.def("terminators", [](llvm::MachineBasicBlock &MB) {
				auto term = MB.terminators();
				return py::make_iterator(term.begin(), term.end());
	    	}, py::keep_alive<0, 1>())
		.def("__repr__",  [](llvm::MachineBasicBlock*MB) {
			return "<llvm::MachineBasicBlock bb." + std::to_string(MB->getNumber()) + "." + MB->getName().str() + ">";
		})
		.def("__str__",  &printToStr<llvm::MachineBasicBlock>)
	    .def("__iter__", [](llvm::MachineBasicBlock &MB) {
	    		return py::make_iterator(MB.begin(), MB.end());
	    	}, py::keep_alive<0, 1>())
		.def("__eq__", [](llvm::MachineBasicBlock & LHS, llvm::MachineBasicBlock & RHS) {
		    return &LHS == &RHS;
	     })
		.def("__hash__", [](llvm::MachineBasicBlock * self) {
			return reinterpret_cast<intptr_t>(self);
		});; /* Keep vector alive while iterator is used */

	py::class_<llvm::MachineOperand, std::unique_ptr<llvm::MachineOperand, py::nodelete>> MachineOperand(m, "MachineOperand");
	MachineOperand
		.def("getReg", &llvm::MachineOperand::getReg)
		.def("getCImm", &llvm::MachineOperand::getCImm, py::return_value_policy::reference_internal)
		.def("getMBB", &llvm::MachineOperand::getMBB, py::return_value_policy::reference)
		.def("getImm", &llvm::MachineOperand::getImm)
		.def("getPredicate", &llvm::MachineOperand::getPredicate)
		.def("getGlobal", &llvm::MachineOperand::getGlobal, py::return_value_policy::reference_internal)
		.def("isReg", &llvm::MachineOperand::isReg)
		.def("isDef", &llvm::MachineOperand::isDef)
		.def("isMBB", &llvm::MachineOperand::isMBB)
		.def("isCImm", &llvm::MachineOperand::isCImm)
		.def("isImm", &llvm::MachineOperand::isImm)
		.def("isPredicate", &llvm::MachineOperand::isPredicate)
		.def("isGlobal", &llvm::MachineOperand::isGlobal)
		.def("getParent", [](llvm::MachineOperand * MO) {
				return MO->getParent();
			}, py::return_value_policy::reference_internal)
		.def("__repr__",  &printToStr<llvm::MachineOperand>);
	py::class_<llvm::MachineMemOperand, std::unique_ptr<llvm::MachineMemOperand, py::nodelete>> MachineMemOperand(m, "MachineMemOperand");
	py::class_<llvm::MachineInstr, std::unique_ptr<llvm::MachineInstr, py::nodelete>> MachineInstr(m, "MachineInstr");
	MachineInstr
		.def("getParent", [](llvm::MachineInstr * MI) {
			return MI->getParent();
		}, py::return_value_policy::reference_internal)
		.def("getNumOperands", &llvm::MachineInstr::getNumOperands)
		.def("getOperand", [](llvm::MachineInstr & I, unsigned i) {
			return I.getOperand(i);
		}, py::return_value_policy::reference_internal)
		.def("getOpcode", [](const llvm::MachineInstr & I) {
			return static_cast<TargetOpcode>(I.getOpcode());
		})
		.def("__repr__",  &printToStr<llvm::MachineInstr>)
		.def("operands", [](llvm::MachineInstr & I) {
						return py::make_iterator(I.operands_begin(), I.operands_end());
					 }, py::keep_alive<0, 1>())
		.def("memoperands", [](llvm::MachineInstr & I) {
			return py::make_iterator(I.memoperands_begin(), I.memoperands_end());
		 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	auto MCII = createGenericFpgaMCInstrInfo();
	py::enum_<TargetOpcode> _TargetOpcode(m, "TargetOpcode");
	for (unsigned i = 0; i < MCII->getNumOpcodes(); i++) {
		_TargetOpcode.value(MCII->getName(i).str().c_str(), static_cast<TargetOpcode>(i));
	}
	_TargetOpcode.export_values();
	delete MCII;

	// [fixme] from some reason the the register object pointer points to deallocated memory in exception handlers (asserts messages)
	py::class_<llvm::Register> Register(m, "Register");
	Register
		.def("id", &llvm::Register::id)
		.def("isVirtual", &llvm::Register::isVirtual)
		.def("virtRegIndex", &llvm::Register::virtRegIndex)
		.def("isPhysical", &llvm::Register::isPhysical)
		.def("__eq__", [](llvm::Register & LHS, llvm::Register & RHS) {
		    return LHS == RHS;
	     })
		.def("__hash__", &llvm::Register::id)
		.def("__repr__", [](llvm::Register*R) {
			std::stringstream ss;
			ss << "<llvm::Register 0x" << std::hex << R->id() <<  ">";
			return ss.str();
		});

	py::class_<llvm::MachineRegisterInfo, std::unique_ptr<llvm::MachineRegisterInfo, py::nodelete>> MachineRegisterInfo(m, "MachineRegisterInfo");
	MachineRegisterInfo
		.def("def_empty", &llvm::MachineRegisterInfo::def_empty)
		.def("getOneDef", &llvm::MachineRegisterInfo::getOneDef, py::return_value_policy::reference_internal);
}

}
