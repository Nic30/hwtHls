#include <hwtHls/llvm/llvmIrLoop.h>

#include <hwtHls/llvm/llvmIrCommon.h>
#include <llvm/Analysis/LoopInfo.h>
#include <hwtHls/llvm/llvmIrMetadata.h>

namespace py = pybind11;

namespace hwtHls {

void register_Loop(pybind11::module_ &m) {
	py::class_<llvm::LoopInfo, std::unique_ptr<llvm::LoopInfo, py::nodelete>> LoopInfo(m, "LoopInfo");
	LoopInfo
		.def("__iter__", [](llvm::LoopInfo &LI) {
			return py::make_iterator(LI.begin(), LI.end());
		 }, py::keep_alive<0, 1>())
		.def("getLoopFor", &llvm::LoopInfo::getLoopFor, "Return the inner most loop that BB lives in. If a basic block is in no"
				" loop (for example the entry node), null is returned.")

		;
	py::class_<llvm::Loop, std::unique_ptr<llvm::Loop, py::nodelete>> Loop(m, "Loop");
	Loop.def("__repr__",  &printToStr<llvm::Loop>)
		.def("getHeader", &llvm::Loop::getHeader, py::return_value_policy::reference_internal)
		.def("getLoopID", [](llvm::Loop & self) {
			return reinterpret_cast<MDNodeWithDeletedDelete*>(self.getLoopID());
		})
		.def("setLoopID",[](llvm::Loop & self, MDNodeWithDeletedDelete*MD) {
			self.setLoopID(MD);
		})
		.def("__iter__", [](llvm::Loop &L) {
			return py::make_iterator(L.begin(), L.end());
		}, py::keep_alive<0, 1>(), "iterate subloops")
		.def("blocks", [](llvm::Loop &L) {
			auto blocks = L.blocks();
			return py::make_iterator(blocks.begin(), blocks.end());
		}, py::keep_alive<0, 1>())
		;
}

}
