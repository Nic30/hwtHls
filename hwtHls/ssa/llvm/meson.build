
subdir('targets')

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
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'], # because of LLVM
    subdir: 'hwtHls/ssa/llvm',
)

