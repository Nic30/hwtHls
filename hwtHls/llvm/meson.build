

py3.extension_module(
    'toLlvm',
    ['llvmIr.cpp',
     'llvmPasses.cpp'],
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    cpp_args: ['-Wno-comment', '-Wno-non-virtual-dtor'], # because of LLVM
    subdir: 'hwtHls/llvm',
)