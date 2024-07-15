
py3.extension_module(
    'abcCpp',
    ['abcCpp.cpp',
     'expandExternalCombLoops.cpp',
     'patternRecognize.cpp',
     ],
    dependencies : [py3_dep, pybind11_dep, berkeley_abc_dep],
    install: true,
    cpp_args: [],
    subdir: 'hwtHls/netlist/abc/',
    include_directories : hwtHls_inc,
)