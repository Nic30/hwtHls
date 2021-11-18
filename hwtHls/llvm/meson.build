

py3.extension_module(
    'toLlvm',
    ['llvmIr.cpp',
     'llvmPasses.cpp'],
    dependencies : [py3_dep, llvm_dep, pybind11_dep],
    install: true,
    subdir: 'hwtHls/llvm',
)