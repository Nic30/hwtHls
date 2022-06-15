#include "llvmIrMachineFunction.h"
#include <sstream>
#include <pybind11/stl.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineLoopInfo.h>
#include <llvm/IR/Constants.h>
#include <llvm/MC/MCInstrInfo.h>

#include "llvmIrCommon.h"
#include "targets/genericFpgaMCTargetDesc.h"

namespace py = pybind11;
enum TargetOpcode: unsigned {};

template<typename ITEM_T>
void register_SmallVector(pybind11::module_ &m, const std::string & name ){
	using vec_t = llvm::SmallVector<ITEM_T>;
	py::class_<vec_t> v(m, name.c_str(), py::module_local(false));
	v
		.def("__iter__", [](vec_t &V) {
				return py::make_iterator(V.begin(), V.end());
		}, py::keep_alive<0, 1>())
		.def("size", &vec_t::size);
}

void register_MachineFunction(pybind11::module_ &m) {
	py::class_<llvm::MachineFunction, std::unique_ptr<llvm::MachineFunction, py::nodelete>> MachineFunction(m, "MachineFunction");
	MachineFunction
		.def("getName", &llvm::MachineFunction::getName)
		.def("__repr__",  [](llvm::MachineFunction*MF) {
			return "<llvm::MachineFunction " + MF->getName().str() + ">";
		})
		.def("__str__",  &printToStr<llvm::MachineFunction>)
		.def("__iter__", [](llvm::MachineFunction &F) {
			return py::make_iterator(F.begin(), F.end());
		}, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

	py::class_<llvm::MachineBasicBlock, std::unique_ptr<llvm::MachineBasicBlock, py::nodelete>> MachineBasicBlock(m, "MachineBasicBlock");
	MachineBasicBlock
		.def("getName", &llvm::MachineBasicBlock::getName)
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
			return "<llvm::MachineBasicBlock " + MB->getName().str() + ">";
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
		.def("getCImm", &llvm::MachineOperand::getCImm)
		.def("getMBB", &llvm::MachineOperand::getMBB)
		.def("getImm", &llvm::MachineOperand::getImm)
		.def("getPredicate", &llvm::MachineOperand::getPredicate)
		.def("isReg", &llvm::MachineOperand::isReg)
		.def("isDef", &llvm::MachineOperand::isDef)
		.def("isMBB", &llvm::MachineOperand::isMBB)
		.def("isCImm", &llvm::MachineOperand::isCImm, py::return_value_policy::reference)
		.def("isImm", &llvm::MachineOperand::isImm)
		.def("isPredicate", &llvm::MachineOperand::isPredicate)
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
		.def("__repr__",  &printToStr<llvm::MachineInstr>)
		.def("operands", [](llvm::MachineInstr & I) {
						return py::make_iterator(I.operands().begin(), I.operands().end());
					 }, py::keep_alive<0, 1>()); /* Keep vector alive while iterator is used */

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
		.def("virtRegIndex", &llvm::Register::virtRegIndex)
		.def("isPhysical", &llvm::Register::isPhysical)
		.def("__eq__", [](llvm::Register & LHS, llvm::Register & RHS) {
		    return LHS == RHS;
	     })
		.def("__hash__", &llvm::Register::id);

	py::class_<llvm::MachineLoopInfo, std::unique_ptr<llvm::MachineLoopInfo, py::nodelete>> MachineLoopInfo(m, "MachineLoopInfo");
	MachineLoopInfo
		.def("isLoopHeader", &llvm::MachineLoopInfo::isLoopHeader)
		.def("getLoopFor", &llvm::MachineLoopInfo::getLoopFor)
		.def("__iter__", [](llvm::MachineLoopInfo &MB) {
				return py::make_iterator(MB.begin(), MB.end());
    	}, py::keep_alive<0, 1>());
	register_SmallVector<llvm::MachineBasicBlock *>(m, "MachineBasicBlockSmallVector");
	register_SmallVector<llvm::MachineLoop::Edge>(m, "MachineEdgeSmallVector");
	py::class_<llvm::MachineLoop, std::unique_ptr<llvm::MachineLoop, py::nodelete>> MachineLoop(m, "MachineLoop");
	MachineLoop
		.def("getParentLoop", &llvm::MachineLoop::getParentLoop)
		.def("getHeader", &llvm::MachineLoop::getHeader)
		.def("getLoopDepth", &llvm::MachineLoop::getLoopDepth)
		.def("hasNoExitBlocks", &llvm::MachineLoop::hasNoExitBlocks)
		.def("isInnermost", &llvm::MachineLoop::isInnermost)
		.def("isOutermost", &llvm::MachineLoop::isOutermost)
		.def("getExitingBlocks", [](llvm::MachineLoop * self) {
			llvm::SmallVector<llvm::MachineBasicBlock *> ExitingBlocks;
			self->getExitingBlocks(ExitingBlocks);
			return ExitingBlocks;
		})
		.def("getExitEdges", [](llvm::MachineLoop * self) {
			llvm::SmallVector<llvm::MachineLoop::Edge> ExitingEdges;
			self->getExitEdges(ExitingEdges);
			return ExitingEdges;
		})
		.def("containsBlock", [](llvm::MachineLoop & L, llvm::MachineBasicBlock & MBB) {
			return L.contains(&MBB);
		})
		.def("getBlocks", [](llvm::MachineLoop &ML) {
				return py::make_iterator(ML.block_begin(), ML.block_end());
    	}, py::keep_alive<0, 1>())
		.def("__str__",  &printToStr<llvm::MachineLoop>);
}
