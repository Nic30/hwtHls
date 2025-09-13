#include <hwtHls/llvm/pybind/llvmIrPassManager.h>

#include <llvm/IR/PassManager.h>
#include <llvm/Pass.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <hwtHls/llvm/Transforms/IoLowerAxiMMPass.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>
#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass.h>


namespace py = pybind11;

namespace hwtHls {

template<typename PassT>
void ModulePassManager_addPass(llvm::ModulePassManager & MPM, PassT pass) {
	MPM.addPass(std::move(pass));
}

template<typename PassT>
void FunctionPassManager_addPass(llvm::FunctionPassManager & FPM, PassT pass) {
	FPM.addPass(std::move(pass));
}

template<typename PassT>
void LoopPassManager_addPass(llvm::LoopPassManager & LPM, PassT pass) {
	LPM.addPass(std::move(pass));
}

void register_PassManager(pybind11::module_ &m) {
	py::class_<ThreadExtractIoFsmPass>(m, "ThreadExtractIoFsmPass")
		.def(py::init());
	py::class_<IoLowerAxiMMPass>(m, "IoLowerAxiMMPass")
		.def(py::init());
	py::class_<LoopFlattenUsingIfPass> _LoopFlattenUsingIfPass(m, "LoopFlattenUsingIfPass");
	_LoopFlattenUsingIfPass
		.def(py::init())
		.def_readonly_static("METADATANAME_MODE", &LoopFlattenUsingIfPass::METADATANAME_MODE)
		;

	py::enum_<LoopFlattenUsingIfPass::Mode> _LoopFlattenUsingIfPassMode(_LoopFlattenUsingIfPass, "Mode");
	_LoopFlattenUsingIfPassMode.value("CHILD_LOOP_ENTRY_IN_SAME_ITERATION", LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_SAME_ITERATION);
	_LoopFlattenUsingIfPassMode.value("CHILD_LOOP_ENTRY_IN_NEXT_ITERATION", LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION);

	py::class_<llvm::ModulePassManager, std::unique_ptr<llvm::ModulePassManager, py::nodelete>>(m, "ModulePassManager")
		.def("addPass", &ModulePassManager_addPass<ThreadExtractIoFsmPass>)
		.def("addPass", &ModulePassManager_addPass<IoLowerAxiMMPass>)
		;
	py::class_<llvm::FunctionPassManager, std::unique_ptr<llvm::FunctionPassManager, py::nodelete>>(m, "FunctionPassManager")
		;
	py::class_<llvm::LoopPassManager, std::unique_ptr<llvm::LoopPassManager, py::nodelete>>(m, "LoopPassManager")
		.def("addPass", &LoopPassManager_addPass<LoopFlattenUsingIfPass>)
		;
}

}
