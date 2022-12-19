#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <memory>
#include <string>
#include <vector>
#include <sstream>

#include "tol.h"

namespace py = pybind11;

namespace hwtHls {

PYBIND11_MODULE(dagQueries, m) {
	py::class_<TOL::ReachabilityIndexTOLButterfly, std::shared_ptr<TOL::ReachabilityIndexTOLButterfly>>(m,
			"ReachabilityIndexTOLButterfly") //
	.def(py::init())
	.def("loadGraph", &TOL::ReachabilityIndexTOLButterfly::loadGraph)
	.def("computeIndex", &TOL::ReachabilityIndexTOLButterfly::computeIndex)
	.def("isReachable", &TOL::ReachabilityIndexTOLButterfly::isReachable)
	.def("computeBacklink", &TOL::ReachabilityIndexTOLButterfly::computeBacklink)
	.def("addEdge", &TOL::ReachabilityIndexTOLButterfly::addEdge)
	.def("addNode", &TOL::ReachabilityIndexTOLButterfly::addNode)
	.def("deleteNode", &TOL::ReachabilityIndexTOLButterfly::deleteNode)
	;

}
}
