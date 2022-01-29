

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
     ],
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'], # because of LLVM
    subdir: 'hwtHls/ssa/llvm',
)