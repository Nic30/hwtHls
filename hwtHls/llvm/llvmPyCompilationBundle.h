#pragma once

#include <pybind11/pybind11.h>

namespace hwtHls {

void register_LlvmCompilationBundle(pybind11::module_ &m);

}
