generated_llvm_backend_files = [
	['HwtFpgaGenGlobalISel.inc', ['-gen-global-isel', ]],
	['HwtFpgaGenInstrInfo.inc', ['-gen-instr-info', ]],
	['HwtFpgaGenRegisterInfo.inc', ['-gen-register-info', ]],
	['HwtFpgaGenSubtargetInfo.inc', ['-gen-subtarget', ]],
	['HwtFpgaGenPreLegalizeGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=HwtFpgaGenPreLegalizeGICombinerHelper']],
	['HwtFpgaGenPreRegAllocGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=HwtFpgaGenPreRegAllocGICombinerHelper']],
	['HwtFpgaGenPreToNetlistGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=HwtFpgaGenPreToNetlistGICombinerHelper']],
]

all_llvm_backend_gen_files = []
foreach f : generated_llvm_backend_files
	gen_src = custom_target(f[0],
	                        input : ['targets/HwtFpgaInstrInfo.td', 'targets/HwtFpgaRegisterInfo.td',
	                                 'targets/HwtFpgaCombine.td', 'targets/HwtFpga.td',
	                                 'targets/HwtFpgaSchedModel.td'],
	                        output : [f[0], ],
	                        command : [llvm_tblgen,
	                        	'-I', llvm_includedir,
	                            '-I', meson.current_source_dir() + '/targets/',
	                        	meson.current_source_dir() + '/targets/HwtFpga.td'] + f[1] + ['-o=@OUTPUT0@', ])
    all_llvm_backend_gen_files += gen_src
endforeach

llmvIr_extraDefs = []
if not llvm_is_debug_build
	llmvIr_extraDefs += ['-DLLVM_NDEBUG=1']
endif

py3.extension_module(
    'llvmIr',
    ['llvmIr.cpp',
     'llvmIrBuilder.cpp',
     'llvmIrFunction.cpp',
     'llvmIrInstruction.cpp',
     'llvmIrValues.cpp',
     'llvmIrStrings.cpp',
     'llvmIrMachineFunction.cpp',
     'llvmIrMachineLoop.cpp',
     'llvmIrMetadata.cpp',
     'llvmCompilationBundle.cpp',

     'llvmSrc/CodeGenPrepare.cpp',
     'targets/Analysis/liveVariableForEdge.cpp',
     'targets/Analysis/registerBitWidth.cpp',


     'targets/intrinsic/bitrange.cpp',

	 'targets/GISel/hwtFpgaCallLoweringInfo.cpp',
	 'targets/GISel/hwtFpgaInstructionSelector.cpp',
	 'targets/GISel/hwtFpgaInstructionSelectorUtils.cpp',
	 'targets/GISel/hwtFpgaLegalizerInfo.cpp',
	 'targets/GISel/hwtFpgaPreLegalizerCombiner.cpp',
	 'targets/GISel/hwtFpgaPreRegAllocCombiner.cpp',
	 'targets/GISel/hwtFpgaPreToNetlistCombiner.cpp',
     'targets/GISel/hwtFpgaRegisterBankInfo.cpp',
     'targets/GISel/hwtFpgaCombinerHelper.cpp',
     'targets/GISel/hwtFpgaCombinerHelperMux.cpp',

	 'targets/hwtFpgaInstrInfo.cpp',
	 'targets/hwtFpgaIoUtils.cpp',
	 'targets/hwtFpgaMCTargetDesc.cpp',
     'targets/hwtFpgaTargetInfo.cpp',
     'targets/hwtFpgaRegisterInfo.cpp',
	 'targets/hwtFpgaTargetLowering.cpp',
     'targets/hwtFpgaTargetSubtarget.cpp',
	 'targets/hwtFpgaTargetMachine.cpp',
     'targets/hwtFpgaTargetTransformInfo.cpp',
     'targets/hwtFpgaTargetPassConfig.cpp',

     'targets/Transforms/machineDumpAndExitPass.cpp',
     'targets/Transforms/hwtFpgaToNetlist.cpp',
     'targets/Transforms/hwtHlsCodeGenPrepare.cpp',
     'targets/Transforms/EarlyMachineCopyPropagation.cpp',

     'Transforms/bitwidthReducePass/bitPartsUseAnalysis.cpp',
     'Transforms/bitwidthReducePass/bitRewriter.cpp',
     'Transforms/bitwidthReducePass/constBitPartsAnalysis.cpp',
     'Transforms/bitwidthReducePass/bitwidthReducePass.cpp',
     'Transforms/bitwidthReducePass/utils.cpp',
     'Transforms/slicesToIndependentVariablesPass/concatMemberVector.cpp',
     'Transforms/slicesToIndependentVariablesPass/detectSplitPoints.cpp',
     'Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.cpp',
     'Transforms/extractBitConcatAndSliceOpsPass.cpp',
     'Transforms/SimplifyCFG2Pass.cpp',
     'Transforms/SimplifyCFG2Pass_normalizeLookupTableIndex.cpp',
     'Transforms/slicesMerge/rewritePhiShift.cpp',
     'Transforms/slicesMerge/rewriteConcat.cpp',
     'Transforms/slicesMerge/slicesMerge.cpp',
     'Transforms/slicesMerge/dceWorklist.cpp',

     ] + all_llvm_backend_gen_files,
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'] + llmvIr_extraDefs, # because of LLVM
    subdir: 'hwtHls/llvm',
)

