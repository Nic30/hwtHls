#include <hwtHls/llvm/pybind/llvmIrPassManager.h>
#include <pybind11/native_enum.h>

#include <llvm/IR/PassManager.h>
#include <llvm/Pass.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/Transforms/IPO/StripDeadPrototypes.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>

#include <hwtHls/llvm/Transforms/BitcountMergePass.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/bitwidthReducePass.h>
#include <hwtHls/llvm/Transforms/HFloatTmpLoweringPass.h>
#include <hwtHls/llvm/Transforms/IoLowerAxiMMPass.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>
#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>
#include <hwtHls/llvm/Transforms/slicesMerge/slicesMerge.h>
#include <hwtHls/llvm/Transforms/LoopRotationNormalizationPass.h>
#include <hwtHls/llvm/Transforms/PruneLoopPhiDeadIncomingValuesPass/PruneLoopPhiDeadIncomingValuesPass.h>
#include <hwtHls/llvm/Transforms/SelectPruningPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/StreamSegmentLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/ThreadExtractPass/ThreadExtractPass.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/ThreadExtractIoFsmPass.h>

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

template<typename PassT, typename FpmT>
void bindFunctionPass(pybind11::module_ &m, FpmT &FunctionPassManager, const char * name) {
	py::class_<PassT>(m, name)
		.def(py::init());
	FunctionPassManager
		.def("addPass", &FunctionPassManager_addPass<PassT>);
}

void register_PassManager(pybind11::module_ &m) {
	// :note: define passes which require some constructor arguments (which bindFunctionPass does not handle)
	py::class_<llvm::StripDeadPrototypesPass>(m, "StripDeadPrototypesPass")
		.def(py::init());
	py::class_<ThreadExtractPass>(m, "ThreadExtractPass")
		.def(py::init());
	py::class_<ThreadExtractIoFsmPass>(m, "ThreadExtractIoFsmPass")
		.def(py::init());
	py::class_<IoLowerAxiMMPass>(m, "IoLowerAxiMMPass")
		.def(py::init());
	py::class_<LoopFlattenUsingIfPass> _LoopFlattenUsingIfPass(m, "LoopFlattenUsingIfPass");
	_LoopFlattenUsingIfPass
		.def(py::init())
		.def_readonly_static("METADATANAME_MODE", &LoopFlattenUsingIfPass::METADATANAME_MODE)
		;

	py::class_<HwtHlsInstCombinePassOptions>(m, "HwtHlsInstCombinePassOptions")
		.def(py::init())
		.def_readwrite("extractBitcounts", &HwtHlsInstCombinePassOptions::extractBitcounts)
		.def_readwrite("bitcountExtractionTreshold", &HwtHlsInstCombinePassOptions::bitcountExtractionTreshold)
		.def_readwrite("computeKnownBitsDepth", &HwtHlsInstCombinePassOptions::computeKnownBitsDepth)
		.def_readwrite("streamReadEoFThreading", &HwtHlsInstCombinePassOptions::streamReadEoFThreading)
		.def_readwrite("hwtHlsFpCombining", &HwtHlsInstCombinePassOptions::hwtHlsFpCombining)
		.def_readwrite("MaxIterations", &HwtHlsInstCombinePassOptions::MaxIterations)
		.def_readwrite("extractBitcounts", &HwtHlsInstCombinePassOptions::extractBitcounts)
		.def_readwrite("extractBitcounts", &HwtHlsInstCombinePassOptions::extractBitcounts)
		;

	py::class_<HwtHlsInstCombinePass>(m, "HwtHlsInstCombinePass")
		.def(py::init<>())
		.def(py::init<HwtHlsInstCombinePassOptions>())
		.def_readonly_static("metadataName_mergableFunction_statePlusMaskedData", &HwtHlsInstCombinePass::metadataName_mergableFunction_statePlusMaskedData)
		.def_readonly_static("metadataName_expr_maskContinuosFromLsb", &HwtHlsInstCombinePass::metadataName_expr_maskContinuosFromLsb)
		;

	py::class_<SlicesToIndependentVariablesPass>(m, "SlicesToIndependentVariablesPass")
		.def(py::init())
		.def_readonly_static("metadataName_NoSplit", &SlicesToIndependentVariablesPass::metadataName_NoSplit);

	py::class_<LoopRotationNormalizationPass> (m, "LoopRotationNormalizationPass")
		.def(py::init());

	py::native_enum<LoopFlattenUsingIfPass::Mode> _LoopFlattenUsingIfPassMode(_LoopFlattenUsingIfPass, "Mode", "enum.Enum");
	_LoopFlattenUsingIfPassMode.value("CHILD_LOOP_ENTRY_IN_SAME_ITERATION", LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_SAME_ITERATION);
	_LoopFlattenUsingIfPassMode.value("CHILD_LOOP_ENTRY_IN_NEXT_ITERATION", LoopFlattenUsingIfPass::Mode::CHILD_LOOP_ENTRY_IN_NEXT_ITERATION);
	_LoopFlattenUsingIfPassMode.finalize();

	py::class_<llvm::ModulePassManager, std::unique_ptr<llvm::ModulePassManager, py::nodelete>>(m, "ModulePassManager")
		.def("addPass", &ModulePassManager_addPass<llvm::StripDeadPrototypesPass>)
		.def("addPass", &ModulePassManager_addPass<ThreadExtractPass>)
		.def("addPass", &ModulePassManager_addPass<ThreadExtractIoFsmPass>)
		.def("addPass", &ModulePassManager_addPass<IoLowerAxiMMPass>)
		;
	py::class_<llvm::FunctionPassManager, std::unique_ptr<llvm::FunctionPassManager, py::nodelete>> FunctionPassManager(m, "FunctionPassManager");
	FunctionPassManager
		.def("addPass", &FunctionPassManager_addPass<HwtHlsInstCombinePass>)
		.def("addPass", &FunctionPassManager_addPass<SlicesToIndependentVariablesPass>)
		;
	bindFunctionPass<llvm::ADCEPass>(m, FunctionPassManager, "ADCEPass");
	bindFunctionPass<llvm::EarlyCSEPass>(m, FunctionPassManager, "EarlyCSEPass");
	bindFunctionPass<BitcountMergePass>(m, FunctionPassManager, "BitcountMergePass");
	bindFunctionPass<BitwidthReductionPass>(m, FunctionPassManager, "BitwidthReductionPass");
	bindFunctionPass<HFloatTmpLoweringPass>(m, FunctionPassManager, "HFloatTmpLoweringPass");
	bindFunctionPass<SlicesMergePass>(m, FunctionPassManager, "SlicesMergePass");
	bindFunctionPass<PruneLoopPhiDeadIncomingValuesPass>(m, FunctionPassManager, "PruneLoopPhiDeadIncomingValuesPass");
	bindFunctionPass<SelectPruningPass>(m, FunctionPassManager, "SelectPruningPass");
	bindFunctionPass<StreamReadLoweringPass>(m, FunctionPassManager, "StreamReadLoweringPass");
	bindFunctionPass<StreamSegmentLoopUnrollPass>(m, FunctionPassManager, "StreamSegmentLoopUnrollPass");


	py::class_<llvm::LoopPassManager, std::unique_ptr<llvm::LoopPassManager, py::nodelete>>(m, "LoopPassManager")
		.def("addPass", &LoopPassManager_addPass<LoopFlattenUsingIfPass>)
		.def("addPass", &LoopPassManager_addPass<LoopRotationNormalizationPass>)
		;
}

}
