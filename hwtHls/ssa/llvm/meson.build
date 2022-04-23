
subdir('targets')

py3.extension_module(
    'llvmIr',
    ['llvmIr.cpp',
     'llvmIrBuilder.cpp',
     'llvmIrInstruction.cpp',
     'llvmIrValues.cpp',
     'llvmIrStrings.cpp',
     'llvmPasses.cpp',
     
     'llvmSrc/CodeGenPrepare.cpp',
     
     'targets/intrinsic/bitrange.cpp',

	 'targets/genericFpgaCallLoweringInfo.cpp',
	 'targets/genericFpgaInstrInfo.cpp',
	 'targets/genericFpgaMCTargetDesc.cpp',
     'targets/genericFpgaTargetInfo.cpp',
     'targets/genericFpgaISelDAGToDAG.cpp',
     'targets/genericFpgaRegisterBankInfo.cpp',
     'targets/genericFpgaRegisterInfo.cpp',
	 'targets/genericFpgaTargetLowering.cpp',
     'targets/genericFpgaTargetSubtarget.cpp',
	 'targets/genericFpgaTargetMachine.cpp',
     'targets/genericFpgaTargetTransformInfo.cpp',
     'targets/genericFpgaTargetPassConfig.cpp',
     
     'targets/Transforms/hwtHlsCodeGenPrepare.cpp',
     
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

