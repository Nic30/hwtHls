# https://mesonbuild.com

project(
  'hwtHls',
  [#'cython',
   'c', 'cpp'],
  # https://stackoverflow.com/questions/59201214/can-the-meson-project-version-be-assigned-dynamically
  version: '0.0', # FIXME: git hash (see URL above).
  license: 'MIT',
  meson_version: '>= 0.60.1',
  default_options: [],
)

# https://github.com/FRidh/mesonpep517examples
# https://github.com/ev-br/mc_lib/blob/master/mc_lib/meson.build
# https://mesonbuild.com/Cython.html
#cython = find_program('cython', required : true)

# https://mesonbuild.com/Python-module.html
py3_mod = import('python')
py3 = py3_mod.find_installation(required: true)
run_command(py3, '-c', 'import sys;  assert sys.version_info >= (3, 10)', check: true)
py3_dep = py3.dependency()
pybind11_inc = run_command(py3, '-c', 'from pybind11 import get_include;  print(get_include())', check: true).stdout().strip()
pybind11_inc = include_directories(pybind11_inc)
pybind11_dep = declare_dependency(
  include_directories : pybind11_inc)


llvm_dep = dependency('llvm', version : '>=14.0.0')
llvm_bin = llvm_dep.get_variable('bindir', default_value:'/usr/lib/llvm-14/bin')
llvm_tblgen = find_program(llvm_bin + '/llvm-tblgen', required: true)

subdir('hwtHls')
