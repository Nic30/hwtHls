#include <memory>
#include <pybind11/detail/common.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/flowmap_yosys.h>
#include <hwtHls/netlist/techmap/flowmap_yosys_areaOpt.h>
#include <hwtHls/netlist/techmap/pool.h>
#include <hwtHls/netlist/techmap/schedulingLutAlap.h>

namespace py = pybind11;
using namespace hwtHls;

PYBIND11_MAKE_OPAQUE(std::vector<HlsNetNodeIn>);
PYBIND11_MAKE_OPAQUE(std::vector<HlsNetNodeOut>);
PYBIND11_MAKE_OPAQUE(std::vector<std::vector<HlsNetNodeIn>>);
PYBIND11_MAKE_OPAQUE(hwtHls::techmap::pool<HlsNetNode*>);
PYBIND11_MAKE_OPAQUE(std::unordered_map<HlsNetNode*, techmap::pool<HlsNetNode*>>);


void bind_poolOfHlsNetNode(py::module &m) {
	using P = hwtHls::techmap::pool<HlsNetNode*>;

    py::class_<P>(m, "PoolOfHlsNetNode")
    .def(py::init<>())
    .def("size", &P::size)
	.def("insert",[](P &self, HlsNetNode*item) {
    	self.insert(item);
    })
	.def("pop", &P::pop)
	.def("__iter__", [](P &self) {
			return py::make_iterator(self.begin(), self.end());
		}, py::keep_alive<0, 1>(), py::return_value_policy::reference_internal)
	;

}

void bind_FlowmapWorker(py::module &m) {
	using FlowmapWorker = hwtHls::techmap::FlowmapWorker;
    py::class_<FlowmapWorker>(m, "FlowmapWorker")
        .def_readwrite("order", &FlowmapWorker::order)
        .def_readwrite("debug", &FlowmapWorker::debug)

		.def_readwrite("nodes", &FlowmapWorker::nodes)
		.def_readwrite("inputs", &FlowmapWorker::inputs)
		.def_readwrite("outputs", &FlowmapWorker::outputs)

		.def_readwrite("edges_fw", &FlowmapWorker::edges_fw)
		.def_readwrite("edges_bw", &FlowmapWorker::edges_bw)
		.def_readwrite("labels", &FlowmapWorker::labels)

		.def_readwrite("lut_nodes", &FlowmapWorker::lut_nodes)
		.def_readwrite("lut_gates", &FlowmapWorker::lut_gates)

        .def("find_subgraph", &FlowmapWorker::find_subgraph)
        .def("build_flow_graph", &FlowmapWorker::build_flow_graph)
        .def("label_nodes", &FlowmapWorker::label_nodes)
        .def("map_luts", &FlowmapWorker::map_luts)
		.def("reset", &FlowmapWorker::reset)

        .def(py::init([](const std::vector<HlsNetNode*>& nodes,
                       const std::vector<HlsNetNode*>& inputs,
                       const std::vector<HlsNetNode*>& outputs,
                       int order, int minlut, bool debug) {
              return new FlowmapWorker(const_cast<std::vector<HlsNetNode*>&>(nodes),
                                     const_cast<std::vector<HlsNetNode*>&>(inputs),
                                     const_cast<std::vector<HlsNetNode*>&>(outputs),
                                     order, minlut, debug);
            }),
            py::arg("nodes"), py::arg("inputs"), py::arg("outputs"),
            py::arg("order") = 3, py::arg("minlut") = 1,
            py::arg("debug") = false)
        ;
	m.def("scheduleLutAlap", techmap::scheduleLutAlap);
	using FlowmapAreaOpt = hwtHls::techmap::FlowmapAreaOpt;
    py::class_<FlowmapAreaOpt>(m, "FlowmapAreaOpt")
		.def(py::init<FlowmapWorker &, int, int, int, bool>(),
				py::arg("fmw"), py::arg("r_alpha") = 8, py::arg("r_beta") = 2,
	            py::arg("r_gamma") = 1, py::arg("debug_relax")=false)
    	.def_readwrite("r_alpha", &FlowmapAreaOpt::r_alpha)
        .def_readwrite("r_beta", &FlowmapAreaOpt::r_beta)
        .def_readwrite("r_gamma", &FlowmapAreaOpt::r_gamma)
        .def_readwrite("debug_relax", &FlowmapAreaOpt::debug_relax)
        //.def("cut_lut_at_gate", &FlowmapAreaOpt::cut_lut_at_gate)
        //.def("check_lut_distances", &FlowmapAreaOpt::check_lut_distances)
        //.def("compute_lut_critical_outputs", &FlowmapAreaOpt::compute_lut_critical_outputs)
        //.def("invalidate_lut_critical_outputs", &FlowmapAreaOpt::invalidate_lut_critical_outputs)
        //.def("check_lut_critical_outputs", &FlowmapAreaOpt::check_lut_critical_outputs)
        //.def("update_lut_critical_outputs", &FlowmapAreaOpt::update_lut_critical_outputs)
        //.def("update_breaking_node_potentials", &FlowmapAreaOpt::update_breaking_node_potentials)
        //.def("relax_depth_for_bound", &FlowmapAreaOpt::relax_depth_for_bound)
        .def("optimize_area", &FlowmapAreaOpt::optimize_area)
		;

}

PYBIND11_MODULE(techmap, m) {
	py::bind_vector<std::vector<HlsNetNodeIn>>(m, "VectorOfHlsNetNodeIn");
	py::bind_vector<std::vector<HlsNetNodeOut>>(m, "VectorOfHlsNetNodeOut");
	py::bind_vector<std::vector<std::optional<HlsNetNodeOut>>>(m, "VectorOfOptionalHlsNetNodeOut");
	py::bind_vector<std::vector<std::vector<HlsNetNodeIn>>>(m, "VectorOfVectorsOfHlsNetNodeIn");
	using UnorderedMapHlsNetNodeToPoolOfHlsNetNode = std::unordered_map<HlsNetNode*, techmap::pool<HlsNetNode*>>;
	py::bind_map<UnorderedMapHlsNetNodeToPoolOfHlsNetNode>(m, "UnorderedMapHlsNetNodeToPoolOfHlsNetNode")
		.def("get", [](const UnorderedMapHlsNetNodeToPoolOfHlsNetNode& map, HlsNetNode* key) -> std::optional<techmap::pool<HlsNetNode*>> {
		    auto it = map.find(key);
		    if (it != map.end())
		    	return it->second;
		    else
		    	return {};
		});;
	m
	.def("clkWindowIndex", &clkWindowIndex)
	.def("clkWindowEnd", &clkWindowEnd)
	.def("clkWindowEndOfPrev", &clkWindowEndOfPrev)
	.def("clkWindowBeginOfNext", &clkWindowBeginOfNext)
	.def("clkWindowOffsetFromWindowBegin", &clkWindowOffsetFromWindowBegin)
	;
	py::class_<HlsNetNode>(m, "HlsNetNode")
		//.def(py::init<>())
		//.def_readwrite("_priv", &HlsNetNode::_priv)
		.def_property_readonly(
			"netlist",
			[](HlsNetNode &self) { return std::unique_ptr<HlsNetlistCtx, py::nodelete>(&self.netlist); },
			py::return_value_policy::reference_internal)
		.def_readonly("_id", &HlsNetNode::_id)
		.def_readonly("_inputs", &HlsNetNode::_inputs)
		.def_readonly("dependsOn", &HlsNetNode::dependsOn)
		.def_readonly("_outputs", &HlsNetNode::_outputs)
		.def_readonly("usedBy", &HlsNetNode::usedBy)
		.def_readonly("flags", &HlsNetNode::flags)
		.def("_addInput", &HlsNetNode::_addInput)
		.def("_addOutput", &HlsNetNode::_addOutput)
		.def(
			"iterInDepNodes",
			[](HlsNetNode &self) {
				auto it = self.iterInDepNodes();
				return py::make_iterator(it.begin(), it.end());
			},
			py::keep_alive<0, 1>())
		.def(
			"iterOutUserNodes",
			[](HlsNetNode &self) {
				auto it = self.iterOutUserNodes();
				return py::make_iterator(it.begin(), it.end());
			},
			py::keep_alive<0, 1>())
		.def_readwrite("scheduledZero", &HlsNetNode::scheduledZero)
		.def_readwrite("scheduledZeroMin", &HlsNetNode::scheduledZeroMin)
		.def_readwrite("scheduledZeroMax", &HlsNetNode::scheduledZeroMax)
		.def_readwrite("scheduledIn", &HlsNetNode::scheduledIn)
		.def_readwrite("scheduledOut", &HlsNetNode::scheduledOut)
		.def_readwrite("isMulticlock", &HlsNetNode::isMulticlock)
		.def_readwrite("scheduleMayBeInFFStoreTime",
					   &HlsNetNode::scheduleMayBeInFFStoreTime)
		.def_readwrite("inputWireDelay", &HlsNetNode::inputWireDelay)
		.def_readwrite("inputClkTickOffset", &HlsNetNode::inputClkTickOffset)
		.def_readwrite("outputWireDelay", &HlsNetNode::outputWireDelay)
		.def_readwrite("outputClkTickOffset", &HlsNetNode::outputClkTickOffset)
		.def("_setScheduleZeroTimeSingleClock",
			 &HlsNetNode::_setScheduleZeroTimeSingleClock)
		.def("_setScheduleZeroTimeMultiClock",
			 &HlsNetNode::_setScheduleZeroTimeMultiClock)
		.def("__eq__", [](const HlsNetNode &self,
						  const HlsNetNode &other) { return &self == &other; })
		.def("__hash__",
			 [](HlsNetNode &self) {
				 return reinterpret_cast<std::uintptr_t>(&self);
			 })
		.def("__repr__", &HlsNetNode::__repr__);

	py::class_<HlsNetNodeFlags>(m, "HlsNetNodeFlags")
        //.def(py::init<>())
        .def_readwrite("isPrimaryIn", &HlsNetNodeFlags::isPrimaryIn)
        .def_readwrite("isPrimaryOut", &HlsNetNodeFlags::isPrimaryOut)
    ;

    py::class_<HlsNetNodeIn>(m, "HlsNetNodeIn")
		//.def(py::init<HlsNetNode&>())
        .def_readonly("obj", &HlsNetNodeIn::obj)
		.def_readonly("in_i", &HlsNetNodeIn::in_i)
        .def("__eq__", &HlsNetNodeIn::operator==)
		.def("__hash__", [](HlsNetNodeIn &self) {
    		return std::hash<HlsNetNodeIn>{}(self);
    	})
		.def("__repr__", [](HlsNetNodeIn &self) {
			std::stringstream ss;
			ss << "<HlsNetNodeIn(cpp) " << self.obj->_id << ":" << self.in_i << ">";
			return ss.str();
		})
    ;

    py::class_<HlsNetNodeOut>(m, "HlsNetNodeOut")
        //.def(py::init<HlsNetNode&>())
        .def_readonly("obj", &HlsNetNodeOut::obj)
        .def_readonly("out_i", &HlsNetNodeOut::out_i)
		.def("connectHlsIn", &HlsNetNodeOut::connectHlsIn)
        .def("__eq__", &HlsNetNodeOut::operator==)
		.def("__hash__", [](HlsNetNodeOut &self) {
		 	 return std::hash<HlsNetNodeOut>{}(self);
		 })
		.def("__repr__", [](HlsNetNodeOut &self) {
			std::stringstream ss;
			ss << "<HlsNetNodeOut(cpp) " << self.obj->_id << ":" << self.out_i << ">";
			return ss.str();
		})
    ;
	py::class_<HlsNetlistCtx>(m, "HlsNetlistCtx")
        .def(py::init<SchedTime, SchedTime>(), py::arg("normalizedClkPeriod"), py::arg("schedFFSetupTime"))
		.def_readonly("schedEpsilon", &HlsNetlistCtx::schedEpsilon)
		.def_readonly("normalizedClkPeriod", &HlsNetlistCtx::normalizedClkPeriod)
		.def_readonly("schedFFSetupTime", &HlsNetlistCtx::schedFFSetupTime)
		.def("createNode", &HlsNetlistCtx::createNode,
			 py::arg("inCnt"), py::arg("outCnt"), py::arg("id")=std::optional<size_t>{},
			 py::return_value_policy::reference_internal)
	;
	bind_poolOfHlsNetNode(m);
	bind_FlowmapWorker(m);
}
