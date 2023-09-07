#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <memory>
#include <string>
#include <vector>
#include <sstream>

#include "../reachabilityCpp/DagGraphWithDFSReachQuery.h"

namespace py = pybind11;

namespace hwtHls::reachability {

PYBIND11_MODULE(reachabilityCpp, m) {

	py::class_<DagGraphWithDFSReachQuery, std::shared_ptr<DagGraphWithDFSReachQuery>>(m, "DagGraphWithDFSReachQuery") //
	.def(py::init<>()) //
	.def("isReachable", &DagGraphWithDFSReachQuery::isReachable) //
	.def("insertEdge", &DagGraphWithDFSReachQuery::insertEdge)  //
	.def("insertNode", &DagGraphWithDFSReachQuery::insertNode, py::return_value_policy::reference_internal)  //
	.def("deleteNode", &DagGraphWithDFSReachQuery::deleteNode)  //
	.def("deleteEdge", &DagGraphWithDFSReachQuery::deleteEdge)  //
			;

	py::class_<Vertex, std::unique_ptr<Vertex, py::nodelete>>(m, "Vertex");

}
}
