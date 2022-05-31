generated_llvm_backend_files = [
	['GenericFpgaGenGlobalISel.inc', ['-gen-global-isel', ]],
	['GenericFpgaGenInstrInfo.inc', ['-gen-instr-info', ]],
	['GenericFpgaGenRegisterInfo.inc', ['-gen-register-info', ]],
	['GenericFpgaGenSubtargetInfo.inc', ['-gen-subtarget', ]],
	['GenericFpgaGenPreLegalizeGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=GenericFpgaGenPreLegalizeGICombinerHelper']],
	['GenericFpgaGenPreRegAllocGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=GenericFpgaGenPreRegAllocGICombinerHelper']],
	['GenericFpgaGenPreToNetlistGICombiner.inc', ['-gen-global-isel-combiner', '-combiners=GenericFpgaGenPreToNetlistGICombinerHelper']],
]

all_llvm_backend_gen_files = []
foreach f : generated_llvm_backend_files
	gen_src = custom_target(f[0],
	                        input : ['targets/GenericFpgaInstrInfo.td', 'targets/GenericFpgaRegisterInfo.td',
	                                 'targets/GenericFpgaCombine.td', 'targets/GenericFpga.td'],
	                        output : [f[0], ],
	                        command : [llvm_tblgen,
	                        	'-I', llvm_includedir,
	                            '-I', meson.current_source_dir() + '/targets/',
	                        	meson.current_source_dir() + '/targets/GenericFpga.td'] + f[1] + ['-o=@OUTPUT0@', ])
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
     'llvmIrInstruction.cpp',
     'llvmIrValues.cpp',
     'llvmIrStrings.cpp',
     'llvmIrMachineFunction.cpp',
     'llvmCompilationBundle.cpp',
     
     'llvmSrc/CodeGenPrepare.cpp',
     'targets/Analysis/liveVariableForEdge.cpp',
     'targets/Analysis/registerBitWidth.cpp',
     
     
     'targets/intrinsic/bitrange.cpp',

	 'targets/GISel/genericFpgaCallLoweringInfo.cpp',
	 'targets/GISel/genericFpgaInstructionSelector.cpp',
	 'targets/GISel/genericFpgaLegalizerInfo.cpp',
	 'targets/GISel/genericFpgaPreLegalizerCombiner.cpp',
	 'targets/GISel/genericFpgaPreRegAllocCombiner.cpp',
	 'targets/GISel/genericFpgaPreToNetlistCombiner.cpp',
     'targets/GISel/genericFpgaRegisterBankInfo.cpp',

	 'targets/genericFpgaInstrInfo.cpp',
	 'targets/genericFpgaMCTargetDesc.cpp',
     'targets/genericFpgaTargetInfo.cpp',
     'targets/genericFpgaRegisterInfo.cpp',
	 'targets/genericFpgaTargetLowering.cpp',
     'targets/genericFpgaTargetSubtarget.cpp',
	 'targets/genericFpgaTargetMachine.cpp',
     'targets/genericFpgaTargetTransformInfo.cpp',
     'targets/genericFpgaTargetPassConfig.cpp',
     
     'targets/Transforms/genericFpgaToNetlist.cpp',
     'targets/Transforms/hwtHlsCodeGenPrepare.cpp',
     'targets/Transforms/EarlyMachineCopyPropagation.cpp',
     
     'Transforms/bitwidthReducePass/bitPartsUseAnalysis.cpp',
     'Transforms/bitwidthReducePass/bitRewriter.cpp',
     'Transforms/bitwidthReducePass/constBitPartsAnalysis.cpp',
     'Transforms/bitwidthReducePass/bitwidthReducePass.cpp',
     'Transforms/bitwidthReducePass/utils.cpp',
     'Transforms/extractBitConcatAndSliceOpsPass.cpp',
     'Transforms/shiftToSelectOfConstShifts.cpp',
     ] + all_llvm_backend_gen_files,
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'] + llmvIr_extraDefs, # because of LLVM
    subdir: 'hwtHls/llvm',
)

