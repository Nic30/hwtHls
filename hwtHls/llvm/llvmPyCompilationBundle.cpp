#include <hwtHls/llvm/llvmPyCompilationBundle.h>

#include <hwtHls/llvm/llvmCompilationBundle.h>
#include <hwtHls/llvm/Transforms/dumpAndExitPass.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/LoopInfo.h>
#include <hwtHls/llvm/targets/hwtFpga.h>
#include <hwtHls/llvm/targets/Transforms/hwtFpgaToNetlist.h>

#include <pybind11/pybind11.h>
// :note: this is important to automatically cast runOpt callback arguments (in runtime)
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>
#include <hwtHls/llvm/llvmIrStripInstrucionUnrelatedToCrash.h>

namespace py = pybind11;

namespace hwtHls {

class ForwardLoopAnalysisPass: public llvm::PassInfoMixin<ForwardLoopAnalysisPass> {
	std::function<void(llvm::LoopInfo&)> callbackFn;
public:
	ForwardLoopAnalysisPass(std::function<void(llvm::LoopInfo&)> callbackFn): callbackFn(callbackFn) {
	}
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		auto &LI = AM.getResult<llvm::LoopAnalysis>(F);
		callbackFn(LI);
		return llvm::PreservedAnalyses::all();
	}
};


void register_LlvmCompilationBundle(pybind11::module_ &m) {
	py::register_local_exception<hwtHls::IntentionalCompilationInterupt>(m, "IntentionalCompilationInterupt", PyExc_RuntimeError);

	py::class_<hwtHls::LlvmCompilationBundle>(m, "LlvmCompilationBundle")
		.def(py::init<const std::string &, const std::vector<hwtHls::LlvmCompilationBundle::LlvmCliOptionTuple> &>())
		.def("getTargetLibraryInfo", &hwtHls::LlvmCompilationBundle::getTargetLibraryInfo)
		.def("runOpt", [](hwtHls::LlvmCompilationBundle * LCB,
				py::function & callbackFn,
				py::function & addExtraModulePasses,
				py::object & hls,
				py::object & toSsa,
				py::object & netlist) {
			py::object returnObj;
			auto callbackFnCpp = [callbackFn, &hls, &toSsa, &netlist, &returnObj](
					llvm::MachineFunction &MF,
					std::set<hwtHls::HwtFpgaToNetlist::MachineBasicBlockEdge>& backedges,
					hwtHls::EdgeLivenessDict & liveness,
					std::vector<llvm::Register> & ioRegs,
					std::map<llvm::Register, unsigned> & registerTypes,
					llvm::MachineLoopInfo & loops) {
				// :note: wrapped in lambda so we can modify reference handling and pass python objects without
				//        spoiling C++ llvm code with pybind11
				returnObj = callbackFn.operator() <py::return_value_policy::reference,
						py::object &,
						py::object &,
						py::object &,
						llvm::MachineFunction &,
						std::set<hwtHls::HwtFpgaToNetlist::MachineBasicBlockEdge>&,
					    hwtHls::EdgeLivenessDict &,
					    std::vector<llvm::Register> &,
					    std::map<llvm::Register, unsigned> &,
					    llvm::MachineLoopInfo &>(
					    		hls, toSsa, netlist, MF, backedges, liveness, ioRegs, registerTypes, loops
				);
			};
			auto addExtraModulePassesCpp = [&addExtraModulePasses](llvm::ModulePassManager &MPM) {
				addExtraModulePasses.operator() <py::return_value_policy::reference, llvm::ModulePassManager &>(std::ref(MPM));
			};

			LCB->runOpt(callbackFnCpp, addExtraModulePassesCpp);
			return returnObj;
		})
		.def("runExprOpt", &hwtHls::LlvmCompilationBundle::runExprOpt)
		.def("runLoopAnalysisGet", [](hwtHls::LlvmCompilationBundle * LCB, py::function & callbackFn) {
			LCB->_runCustomFunctionPass([&callbackFn](llvm::FunctionPassManager &FPM) {
				FPM.addPass(ForwardLoopAnalysisPass([&callbackFn](llvm::LoopInfo &LI) {
					callbackFn.operator() <py::return_value_policy::reference, llvm::LoopInfo &>(LI);
				}));
			});
		})
		.def("registerAfterPassCallbackForIr", [](hwtHls::LlvmCompilationBundle * self, py::function & callbackFn) {
			self->PIC.registerAfterPassCallback([callbackFn](llvm::StringRef PassName, llvm::Any IR, const llvm::PreservedAnalyses& PA) {
				try {
				    callbackFn.operator() <py::return_value_policy::reference, llvm::StringRef&, llvm::Any&>(PassName, IR);
				} catch (py::error_already_set & e) {
					throw e; // this is useful if you want to use debugger to break on exception raised in python callback
				}
			});
		})
		.def("registerAfterPassCallbackForMir", [](hwtHls::LlvmCompilationBundle * self, py::function & callbackFn) {
			self->PICForLegacyPM.registerAfterPassCallback([callbackFn](llvm::StringRef PassName, llvm::Any IR, const llvm::PreservedAnalyses& PA) {
				 callbackFn.operator() <py::return_value_policy::reference, llvm::StringRef&, llvm::Any&>(PassName, IR);
			});
		})
		.def("getMachineFunction", &hwtHls::LlvmCompilationBundle::getMachineFunction, py::return_value_policy::reference_internal)
		.def("getMachineModuleInfo", &hwtHls::LlvmCompilationBundle::getMachineModuleInfo, py::return_value_policy::reference_internal)
		.def("_tryToFindMain",  &hwtHls::LlvmCompilationBundle::_tryToFindMain)
		.def("_testHwtHlsSimplifyCFGPass", &hwtHls::LlvmCompilationBundle::_testHwtHlsSimplifyCFGPass,
				py::kw_only(),
				py::arg("BonusInstThreshold").noconvert() = 1,
				py::arg("ForwardSwitchCondToPhi").noconvert() = false,
				py::arg("ConvertSwitchRangeToICmp").noconvert() = false,
				py::arg("ConvertSwitchToLookupTable").noconvert() = false,
				py::arg("NeedCanonicalLoops").noconvert() = true,
				py::arg("HoistCommonInsts").noconvert() = false,
				py::arg("SinkCommonInsts").noconvert() = false,
				py::arg("SimplifyCondBranch").noconvert() = true,
				py::arg("HoistCheapInsts").noconvert() = false,
				py::arg("dumpDotBeforeToFile") = std::optional<std::string>(),  //
				py::arg("dumpDotAfterToFile") = std::optional<std::string>(),   //
				py::arg("dumpCfgBeforeToFile") = std::optional<std::string>(),  //
				py::arg("dumpCfgAfterToFile") = std::optional<std::string>(),    //
				py::return_value_policy::reference_internal)
		.def("_runCustomModulePass", [](hwtHls::LlvmCompilationBundle & self, py::function & addModulePassesFn) -> llvm::Module& {
			return self._runCustomModulePass([&addModulePassesFn](llvm::ModulePassManager& MPM) {
					addModulePassesFn.operator() <py::return_value_policy::reference, llvm::ModulePassManager&>(MPM);
				});
	    }, py::return_value_policy::reference_internal)
		.def("_runCustomFunctionPass", [](hwtHls::LlvmCompilationBundle & self, py::function & addFunctionPassesFn) -> llvm::Function& {
			return self._runCustomFunctionPass([&addFunctionPassesFn](llvm::FunctionPassManager& FPM) {
					addFunctionPassesFn.operator() <py::return_value_policy::reference, llvm::FunctionPassManager&>(FPM);
				});
	    }, py::return_value_policy::reference_internal)
		.def("_runCustomLoopPass", [](hwtHls::LlvmCompilationBundle & self, py::function & addLoopPassesFn) -> llvm::Function& {
			return self._runCustomLoopPass([&addLoopPassesFn](llvm::LoopPassManager& LPM) {
					addLoopPassesFn.operator() <py::return_value_policy::reference, llvm::LoopPassManager&>(LPM);
				});
	    }, py::return_value_policy::reference_internal)
		.def("_testEarlyIfConverter", &hwtHls::LlvmCompilationBundle::_testEarlyIfConverter, py::return_value_policy::reference_internal)
		.def("_testHwtFpgaPreRegAllocGICombiner", &hwtHls::LlvmCompilationBundle::_testHwtFpgaPreRegAllocGICombiner, py::return_value_policy::reference_internal)
		.def("_testHwtFpgaPreToNetlistCombiner", &hwtHls::LlvmCompilationBundle::_testHwtFpgaPreToNetlistCombiner, py::return_value_policy::reference_internal)
		.def("_testLoopFlattenUsingIfPass", &hwtHls::LlvmCompilationBundle::_testLoopFlattenUsingIfPass, py::return_value_policy::reference_internal)
		.def("_testRewriteExtractOnMergeValuesPass", &hwtHls::LlvmCompilationBundle::_testRewriteExtractOnMergeValues, py::return_value_policy::reference_internal)
		.def("_testVRegIfConverter", &hwtHls::LlvmCompilationBundle::_testVRegIfConverter, py::return_value_policy::reference_internal)
		.def("_testVRegIfConverterForIr", &hwtHls::LlvmCompilationBundle::_testVRegIfConverterForIr, py::return_value_policy::reference_internal)
		.def("_testStripInstrucionUnrelatedToCrash", [](hwtHls::LlvmCompilationBundle &self,
													    size_t nprocs,
														py::function testFunction,
														bool logAfterChange,
														std::optional<double> timeout) {
			llvmIrStripInstrucionUnrelatedToCrash(self, nprocs, [&testFunction](hwtHls::LlvmCompilationBundle &ctx) {
				testFunction(ctx);
			}, logAfterChange, timeout);
	    }, py::arg("nprocs"),
		   py::arg("testFunction"),
		   py::arg("logAfterChange")=false,
		   py::arg("timeout")=std::optional<double>())
		.def_readonly("ctx", &hwtHls::LlvmCompilationBundle::ctx)
		.def_readonly("strCtx", &hwtHls::LlvmCompilationBundle::strCtx)
		.def_readonly("builder", &hwtHls::LlvmCompilationBundle::builder)
		.def_readwrite("main", &hwtHls::LlvmCompilationBundle::main)
		.def_readwrite("module", &hwtHls::LlvmCompilationBundle::module);

}

}
