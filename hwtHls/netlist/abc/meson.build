
lib_berkeley_abc_patternRecognize_static = static_library(
  'berkeley_abc_patternRecognize',
  [
       'patternRecognize.cpp',
  ],
  dependencies: [berkeley_abc_dep],
  include_directories : hwtHls_inc)

lib_berkeley_abc_patternRecognize_static_dep = declare_dependency(
	include_directories : hwtHls_inc,
  	link_with : lib_berkeley_abc_patternRecognize_static)

py3.extension_module(
    'abcCpp',
    ['abcCpp.cpp',
     'expandExternalCombLoops.cpp',
     ],
    dependencies : [py3_dep, pybind11_dep, berkeley_abc_dep, lib_berkeley_abc_patternRecognize_static_dep],
    install: true,
    cpp_args: [],
    subdir: 'hwtHls/netlist/abc/',
    include_directories : hwtHls_inc,
)