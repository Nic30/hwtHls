#include "llvmIrMachineLoop.h"

#include "llvmIrCommon.h"
#include <llvm/CodeGen/MachineLoopInfo.h>

namespace py = pybind11;

namespace hwtHls {

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

void register_MachineLoop(pybind11::module_ &m) {
	py::class_<llvm::MachineLoopInfo, std::unique_ptr<llvm::MachineLoopInfo, py::nodelete>> MachineLoopInfo(m, "MachineLoopInfo");
	MachineLoopInfo
		.def("isLoopHeader", &llvm::MachineLoopInfo::isLoopHeader)
		.def("getLoopFor", &llvm::MachineLoopInfo::getLoopFor, py::return_value_policy::reference_internal)
		.def("__iter__", [](llvm::MachineLoopInfo &MLI) {
				return py::make_iterator(MLI.begin(), MLI.end());
    	}, py::keep_alive<0, 1>());
	register_SmallVector<llvm::MachineBasicBlock *>(m, "MachineBasicBlockSmallVector");
	register_SmallVector<llvm::MachineLoop::Edge>(m, "MachineEdgeSmallVector");
	py::class_<llvm::MachineLoop, std::unique_ptr<llvm::MachineLoop, py::nodelete>> MachineLoop(m, "MachineLoop");
	MachineLoop
		.def("getParentLoop", &llvm::MachineLoop::getParentLoop, py::return_value_policy::reference)
		.def("getHeader", &llvm::MachineLoop::getHeader, py::return_value_policy::reference)
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
		.def("__iter__", [](llvm::MachineLoop &ML) {
				return py::make_iterator(ML.begin(), ML.end());
		}, py::keep_alive<0, 1>())
		.def("__str__",  &printToStr<llvm::MachineLoop>);
}

}
