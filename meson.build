project(
  'hwtHls',
  ['c', 'cpp'],
  # https://stackoverflow.com/questions/59201214/can-the-meson-project-version-be-assigned-dynamically
  version: '0.0', # FIXME: git hash (see URL above).
  license: 'MIT',
  meson_version: '>= 1.1.0',
  default_options: ['cpp_std=c++20'],
)

py3_mod = import('python')
py3 = py3_mod.find_installation(required: true)
run_command(py3, '-c', 'import sys;  assert sys.version_info >= (3, 12)', check: true)
py3_dep = py3.dependency()
pybind11_inc = run_command(py3, '-c', 'from pybind11 import get_include;  print(get_include())', check: true).stdout().strip()
pybind11_inc = include_directories(pybind11_inc)
pybind11_dep = declare_dependency(
  include_directories : pybind11_inc)

llvm_dep = dependency('llvm', method: 'config-tool', version : '>=16.0.0')
llvm_bin = llvm_dep.get_variable('bindir')
llvm_includedir = llvm_dep.get_variable('includedir')
llvm_tblgen = find_program(llvm_bin + '/llvm-tblgen', required: true)
llvm_is_debug_build = llvm_dep.get_variable('build-mode',  default_value: 'Release') == 'Debug'

# berkeley-abc related
# dependency('readline') # to trigger error sooner if readline is not installed for berkeley-abc
cmake = import('cmake')
berkeley_abc_opt_var = cmake.subproject_options()
# berkeley_abc_opt_var.add_cmake_defines({'ABC_NAMESPACE': 'abc'})
# berkeley_abc_opt_var.add_cmake_defines({'ABC_USE_NO_READLINE': 1})
BERKELEY_ABC_CXX_FLAGS = (
	'-Wno-unused-variable -Wno-unused-function -Wno-sign-compare -Wno-unused-but-set-variable -Wno-write-strings ' +
	'-Wno-format-overflow -Wno-maybe-uninitialized -Wno-alloc-size-larger-than -Wno-array-bounds -Wno-nonnull ' + 
	'-Wno-stringop-overflow')
berkeley_abc_opt_var.add_cmake_defines({
  'CMAKE_BUILD_TYPE': 'Release',
  'CMAKE_C_FLAGS': BERKELEY_ABC_CXX_FLAGS + ' -Wno-int-conversion -Wno-implicit-function-declaration',
  'CMAKE_CXX_FLAGS': BERKELEY_ABC_CXX_FLAGS,
})
berkeley_abc_proj = cmake.subproject('berkeley-abc', options: berkeley_abc_opt_var)
berkeley_abc_dep = berkeley_abc_proj.dependency('libabc-pic')
hwtHls_inc = include_directories('.')
subdir('hwtHls')
