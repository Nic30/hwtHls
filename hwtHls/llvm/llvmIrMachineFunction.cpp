#include "llvmIrMachineFunction.h"
#include "llvmIrCommon.h"
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/IR/Constants.h>
#include <llvm/MC/MCInstrInfo.h>
#include "targets/genericFpgaMCTargetDesc.h"
#include <sstream>

namespace py = pybind11;
enum TargetOpcode: unsigned {};

void register_MachineFunction(pybind11::module_ &m) {
	py::class_<llvm::MachineFunction, std::unique_ptr<llvm::MachineFunction, py::nodelete>> MachineFunction(m, "MachineFunction");
	MachineFunction
		.def("__repr__",  [](llvm::MachineFunction*MF) {
			return "<llvm::MachineFunction " + MF->getName().str() + ">";
		})
		.def("__str__",  &printToStr<llvm::MachineFunction>)
		.def("__iter__", [](llvm::MachineFunction &F) {
						return py::make_iterator(F.begin(), F.end());
					 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::MachineBasicBlock, std::unique_ptr<llvm::MachineBasicBlock, py::nodelete>> MachineBasicBlock(m, "MachineBasicBlock");
	MachineBasicBlock
		.def("__repr__",  [](llvm::MachineBasicBlock*MB) {
			return "<llvm::MachineBasicBlock " + MB->getName().str() + ">";
		})
		.def("getName", &llvm::MachineBasicBlock::getName)
		.def("__str__",  &printToStr<llvm::MachineBasicBlock>)
	    .def("__iter__", [](llvm::MachineBasicBlock &F) {
	    		return py::make_iterator(F.begin(), F.end());
	    	}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::MachineOperand, std::unique_ptr<llvm::MachineOperand, py::nodelete>> MachineOperand(m, "MachineOperand");
	MachineOperand
		.def("getReg", &llvm::MachineOperand::getReg)
		.def("getCImm", &llvm::MachineOperand::getCImm)
		.def("isReg", &llvm::MachineOperand::isReg)
		.def("isCImm", &llvm::MachineOperand::isCImm, py::return_value_policy::reference)
		.def("__repr__",  &printToStr<llvm::MachineOperand>);

	py::class_<llvm::MachineInstr, std::unique_ptr<llvm::MachineInstr, py::nodelete>> MachineInstr(m, "MachineInstr");
	MachineInstr
		.def("getNumOperands", &llvm::MachineInstr::getNumOperands)
		.def("getOperand", [](llvm::MachineInstr & I, unsigned i) {
			return I.getOperand(i);
		})
		.def("getOpcode", [](const llvm::MachineInstr & I) {
			return static_cast<TargetOpcode>(I.getOpcode());
		})
		.def("__repr__",  &printToStr<llvm::MachineInstr>);

	auto MCII = createGenericFpgaMCInstrInfo();
	py::enum_<TargetOpcode> _TargetOpcode(m, "TargetOpcode");
	for (unsigned i = 0; i < MCII->getNumOpcodes(); i++) {
		_TargetOpcode.value(MCII->getName(i).str().c_str(), static_cast<TargetOpcode>(i));
	}
	_TargetOpcode.export_values();
	delete MCII;

	py::class_<llvm::Register> Register(m, "Register");
	Register
		.def("__repr__", [](llvm::Register*R) {
			std::stringstream ss;
			ss << "<llvm::Register 0x" << std::hex << R->id() <<  ">";
			return ss.str();
		})
		.def("id", &llvm::Register::id)
		.def("isVirtual", &llvm::Register::isVirtual)
		.def("isPhysical", &llvm::Register::isPhysical);

}
