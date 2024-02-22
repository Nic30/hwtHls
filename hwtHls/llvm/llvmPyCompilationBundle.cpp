#include <hwtHls/llvm/llvmPyCompilationBundle.h>

#include <hwtHls/llvm/llvmCompilationBundle.h>
#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <hwtHls/llvm/targets/hwtFpga.h>
#include <hwtHls/llvm/targets/Transforms/hwtFpgaToNetlist.h>

#include <pybind11/pybind11.h>
// :note: this is important to automatically cast runOpt callback arguments (in runtime)
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

namespace py = pybind11;

namespace hwtHls {

void register_LlvmCompilationBundle(pybind11::module_ &m) {
	py::register_local_exception<hwtHls::IntentionalCompilationInterupt>(m, "IntentionalCompilationInterupt", PyExc_RuntimeError);

	py::class_<hwtHls::LlvmCompilationBundle>(m, "LlvmCompilationBundle")
		.def(py::init<const std::string &>())
		.def("addLlvmCliArgOccurence", &hwtHls::LlvmCompilationBundle::addLlvmCliArgOccurence)
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
		.def("runExprOpt", &hwtHls::LlvmCompilationBundle::runExprOpt)
		.def("registerAfterPassCallback", [](hwtHls::LlvmCompilationBundle * self, py::function & callbackFn) {
			self->PIC.registerAfterPassCallback([callbackFn](llvm::StringRef PassName, llvm::Any IR, const llvm::PreservedAnalyses& PA) {
				 callbackFn.operator() <py::return_value_policy::reference, llvm::StringRef&, llvm::Any&>(PassName, IR);
			 });
		})
		.def("getMachineFunction", &hwtHls::LlvmCompilationBundle::getMachineFunction, py::return_value_policy::reference_internal)
		.def("getMachineModuleInfo", &hwtHls::LlvmCompilationBundle::getMachineModuleInfo, py::return_value_policy::reference_internal)
		.def("_testSlicesToIndependentVariablesPass", &hwtHls::LlvmCompilationBundle::_testSlicesToIndependentVariablesPass, py::return_value_policy::reference_internal)
		.def("_testSlicesMergePass", &hwtHls::LlvmCompilationBundle::_testSlicesMergePass, py::return_value_policy::reference_internal)
		.def("_testLoopUnrotatePass", &hwtHls::LlvmCompilationBundle::_testLoopUnrotatePass, py::return_value_policy::reference_internal)
		.def("_testBitwidthReductionPass", &hwtHls::LlvmCompilationBundle::_testBitwidthReductionPass, py::return_value_policy::reference_internal)
		.def("_testRewriteExtractOnMergeValuesPass", &hwtHls::LlvmCompilationBundle::_testRewriteExtractOnMergeValues, py::return_value_policy::reference_internal)
		.def("_testEarlyIfConverter", &hwtHls::LlvmCompilationBundle::_testEarlyIfConverter, py::return_value_policy::reference_internal)
		.def("_testVRegIfConverter", &hwtHls::LlvmCompilationBundle::_testVRegIfConverter, py::return_value_policy::reference_internal)
		.def("_testVRegIfConverterForIr", &hwtHls::LlvmCompilationBundle::_testVRegIfConverterForIr, py::return_value_policy::reference_internal)
		.def_readonly("ctx", &hwtHls::LlvmCompilationBundle::ctx)
		.def_readonly("strCtx", &hwtHls::LlvmCompilationBundle::strCtx)
		.def_readonly("builder", &hwtHls::LlvmCompilationBundle::builder)
		.def_readwrite("main", &hwtHls::LlvmCompilationBundle::main)
		.def_readwrite("module", &hwtHls::LlvmCompilationBundle::module);

}

}
