

py3.extension_module(
    'llvmIr',
    ['llvmIr.cpp',
     'llvmIrBuilder.cpp',
     'llvmIrInstruction.cpp',
     'llvmIrValues.cpp',
     'llvmIrStrings.cpp',
     'llvmPasses.cpp',
     
     'targets/MCTargetDesc/genericFpgaMCTargetDesc.cpp',
     'targets/TargetInfo/genericFpgaTargetInfo.cpp',
     'targets/intrinsic/bitrange.cpp',
     'targets/genericFpgaSubtarget.cpp',
	 'targets/genericFpgaTargetMachine.cpp',
     'targets/genericFpgaTargetTransformInfo.cpp',
     
     'Transforms/extractBitConcatAndSliceOpsPass.cpp',
     
     'Transforms/constBitPropagation/bitPartsUseAnalysis.cpp',
     'Transforms/constBitPropagation/bitRewriter.cpp',
     'Transforms/constBitPropagation/constBitPartsAnalysis.cpp',
     'Transforms/constBitPropagation/constBitPropagationPass.cpp',
     'Transforms/constBitPropagation/utils.cpp',
     ],
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'], # because of LLVM
    subdir: 'hwtHls/ssa/llvm',
)