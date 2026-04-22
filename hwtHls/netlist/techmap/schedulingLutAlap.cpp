#include <cassert>
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/schedulingAlap.h>
#include <hwtHls/netlist/techmap/schedulingLutAlap.h>
#include <limits>
#include <queue>
#include <ranges>
#include <unordered_map>

namespace hwtHls::techmap {

void scheduleLutAlapResetSchedule(FlowmapWorker &fmw, SchedTime &lutDelay) {
	// set delays of nodes which are not primary in/out
	// to 0 or lutDelay if the node is picked as representator of LUT
	for (auto *n : fmw.nodes) {
		if (fmw.inputs.contains(n) || fmw.outputs.contains(n))
			continue;
		n->scheduledZero = {};
		SchedTime inDelay = 0;
		if (fmw.lut_nodes.contains(n)) {
			inDelay = lutDelay;
		}
		std::fill(n->inputWireDelay.begin(), n->inputWireDelay.end(), 0);
		std::fill(n->inputClkTickOffset.begin(), n->inputClkTickOffset.end(),
				  inDelay);

		std::fill(n->outputWireDelay.begin(), n->outputWireDelay.end(), 0);
		std::fill(n->outputClkTickOffset.begin(), n->outputClkTickOffset.end(),
				  0);
	}
}

void scheduleLutAlapInitOutUserCnt(
	const pool<HlsNetNode *> &nodes,
	const std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> &edges_fw,
	std::queue<HlsNetNode *> &ready) {
	// :note: reverse_view to have outputs which were likely constructed last
	// time as first
	for (HlsNetNode *node : std::ranges::reverse_view(nodes)) {
		auto succs = edges_fw.find(node);
		OutUserCounter outdeg = 0;
		if (succs != edges_fw.end())
			for (auto *suc : succs->second)
				if (nodes.contains(suc))
					outdeg++;
		// std::cout << "indeg: " << node->__repr__() << " " << indeg <<
		// std::endl;
		getOutUserCount(*node) = outdeg;
		if (outdeg == 0)
			ready.push(node);
	}
}

void scheduleLutAlapCopySchedulingFromLutRepresentatorsToRestOfNodes(
	FlowmapWorker &fmw, SchedTime lutDelay, SchedTime endOfLastClk) {

	// backup original times because nodes representing LUT may be a member node
	// of other LUT an by update of time for node we would loose the time for
	// LUT where this node is primary output
	std::vector<std::pair<HlsNetNode *, SchedTime>> lutTimes;
	lutTimes.reserve(fmw.lut_nodes.size());
	for (auto *lut : fmw.lut_nodes) {
		assert(lut->scheduledZero.has_value());
		assert(!lut->scheduledIn.empty());
		lutTimes.push_back({lut, lut->scheduledZero.value()});
	}
	for (const auto &[lut, time] : lutTimes) {
		auto clkPeriod = lut->netlist.normalizedClkPeriod;
		SchedTime t = time;
		bool isPrimaryOut = lut->_outputs.empty();
		if (isPrimaryOut) {
			// :note: LUT delay is at outputs side
			if (clkWindowIndex(t, clkPeriod) != clkWindowIndex(t - lutDelay, clkPeriod)) {
				// if LUT composed of nodes driving this PO would cross clk window boundary, we have to map it
				// at the end of previous clock cycle
				t = clkWindowEndOfPrev(t, clkPeriod);
				t -= lut->netlist.schedFFSetupTime;
			}
			//t -= lutDelay;
		}
		auto _lutGates = fmw.lut_gates.find(lut);
		if (_lutGates != fmw.lut_gates.end()) {
			for (auto *gate : _lutGates->second) {
				if (gate == lut)
					continue; 
				auto _t = t;
				bool isPrimaryIn = gate->_inputs.empty();
				if (isPrimaryIn)
					_t = t - lutDelay; // push this node on time where this LUT starts
				if ((!gate->scheduledZero.has_value() ||
					gate->scheduledZero.value() > _t)) {
					gate->_setScheduleZeroTimeSingleClock(_t);
				}
			}
		}
		if (!isPrimaryOut) {
			if (!lut->scheduledZero.has_value() ||
				lut->scheduledZero.value() > time) {
				lut->_setScheduleZeroTimeSingleClock(time);
			}
		}
	}
	// primary inputs/outputs are not required to be a part of any LUT
	for (auto pi : fmw.inputs) {
		if (!pi->scheduledZero.has_value()) {
			SchedTime t = endOfLastClk;
			for (auto &users : pi->usedBy) {
				for (auto use : users) {
					assert(use.obj->scheduledZero.has_value());
					auto useT = use.obj->scheduledIn[use.in_i] - lutDelay;
					t = std::min(t, useT);
				}
			}
			pi->_setScheduleZeroTimeSingleClock(t);
		}
	}
	
	for (auto po : fmw.outputs) {
		if (!po->scheduledZero.has_value()) {
			SchedTime t = std::numeric_limits<SchedTime>::min();
			assert(!po->dependsOn.empty());
			for (auto _dep : po->dependsOn) {
				assert(_dep.has_value());
				auto &dep = _dep.value();
				assert(dep.obj->scheduledZero.has_value());
				auto depT = dep.obj->scheduledOut[dep.out_i];
				t = std::max(t, depT);
			}
			po->_setScheduleZeroTimeSingleClock(t);
		}
	}
}

class HlsNetNodeWithMaxTimeRAII {
	HlsNetNode &n;
	std::optional<SchedTime> origMaxTime;

public:
	HlsNetNodeWithMaxTimeRAII(HlsNetNode &n, SchedTime t) :
		n(n), origMaxTime(n.scheduledZeroMax) {
		n.scheduledZeroMax = t;
	}
	~HlsNetNodeWithMaxTimeRAII() { n.scheduledZeroMax = origMaxTime; }
};

void scheduleLutAlap(FlowmapWorker &fmw, SchedTime lutDelay,
					 SchedTime endOfLastClk) {
	assert(lutDelay > 0);
	// :note: the lutDelay is used as inputWireDelay of all nodes which are
	// representing the LUT, all other nodes will have all delays zero
	scheduleLutAlapResetSchedule(fmw, lutDelay);

	const pool<HlsNetNode *> &nodes = fmw.lut_nodes;
	const HlsNetlistCtx &netlist = (*fmw.nodes.begin())->netlist;
	assert((endOfLastClk % netlist.normalizedClkPeriod) == 0);
	// nodes.reserve(fmw.inputs.size() + fmw.outputs.size() +
	//			  fmw.lut_nodes.size());
	// nodes.reserve(fmw.outputs.size());

	// std::ranges::views::concat(fmw.inputs, fmw.lut_nodes, fmw.outputs)
	// for (auto n : fmw.lut_nodes) {
	//	nodes.insert(n);
	//}
	//
	// :note: in LUT graph the edges_fw successors can contain also nodes which
	// are inside of LUT, but the LUT is represented by
	//   some other node, those nodes must be skipped

	// Kahn's algorithm (BFS) for reverse topological order (sinks first)
	// Initialize indegrees: count outputs with users
	std::queue<HlsNetNode *> readyNodes;
	const auto &edges_bw = fmw.lut_edges_bw;
	const auto &edges_fw = fmw.lut_edges_fw;
	// :note: edges_fw/edges_bw may be empty, for example if the graph contains
	// only 1 level of LUTs

	// assert(fmw.lut_edges_fw.size() == 0);
	//  reconstruct edges_fw
	// std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> edges_fw;
	// for (const auto &[user, deps] : edges_bw) {
	//	for (HlsNetNode* dep: deps) {
	//		auto users = edges_fw.find(dep);
	//		if (users == edges_fw.end()) {
	//			edges_fw[dep] = {user};
	//		} else {
	//			users->second.insert(user);
	//		}
	//	}
	// }
	scheduleLutAlapInitOutUserCnt(nodes, edges_fw, readyNodes);
	if (!nodes.empty()) {
		assert(!readyNodes.empty());
	}
	const pool<HlsNetNode *> nullSucc = {nullptr};
	const pool<HlsNetNode *> noSucc = {};

	while (!readyNodes.empty()) {
		// :note: node is known to have all successors scheduled
		// :note: this loop itertes only nodes which were picked as LUT representators
		HlsNetNode *node = readyNodes.front();
		readyNodes.pop();
		auto _endOfLastClk = endOfLastClk;
		bool isPrimaryOutput = false;
		if (node->scheduledZero.has_value()) {
			assert(node->_outputs.empty() && "Only primary output may have time specified before scheduling");
			// :note: even if the node is scheduled primary output we may
			// optionally move it
			//  to previous clock window if the LUT it represents does not fit
			//  between scheduled time an the beginning of clock window
			_endOfLastClk = node->scheduledZero.value();
			node->resetScheduling();

			std::fill(node->inputWireDelay.begin(), node->inputWireDelay.end(),
					  0);
			std::fill(node->outputWireDelay.begin(),
					  node->outputWireDelay.end(), 0);
			isPrimaryOutput = true;
		} else {
			// temporary increase delay so the node represents the delay of actual
			// lut, we need this for clock window boundary crossing check
			std::fill(node->inputWireDelay.begin(), node->inputWireDelay.end(),
					  lutDelay);
		}
		// :note: primary outputs are already scheduled
		auto sucNodes = edges_fw.find(node);

		const auto &netlist = node->netlist;
		SchedTime ffdelay = netlist.schedFFSetupTime;
		SchedTime clkPeriod = netlist.normalizedClkPeriod;
		SchedTime nodeZeroTime = std::numeric_limits<SchedTime>::max();
		if (lutDelay + ffdelay >= clkPeriod) {
			throw TimeConstraintError("clkPeriod too low for LUT delays");
		}

		std::optional<SchedTime> curZero = node->scheduledZero;
		auto *directSucs = &noSucc;
		if (sucNodes == edges_fw.end() || sucNodes->second.empty()) {
			// no outputs, we must use some asap input time and move to end
			// of the clock
			// assert(!node->_inputs.empty() &&
			//	   "Node must have at least some port");
		} else {
			directSucs = &sucNodes->second;
		}

		auto sucs = std::ranges::views::concat(*directSucs, nullSucc);
		for (auto suc : sucs) {
			if (suc && !nodes.contains(suc))
				continue; // some successor which is part of lut where other
						  // node is representator,
			// we can ignore this node as the LUT representator is also in
			// successors
			SchedTime outWireLatency =
				node->_outputs.empty() ? 0 : node->outputWireDelay[0];
			// find earliest time where this output is used
			SchedTime inpTime;
			if (suc) {
				assert(suc->scheduledZero);
				inpTime = suc->scheduledZero.value() - lutDelay;
			} else if (!isPrimaryOutput) {
				continue;
			} else {
				// :note: special case where we may have to move primary
				//  input representing the LUT to previous clock window
				//  because LUT would not fit in space between schedule of
				//  node and the beginning of the clock window
				inpTime = _endOfLastClk;// - lutDelay;
			}
			if (curZero.has_value()) {
				assert(inpTime >= curZero.value() &&
					   "Current output violates input time");
			}

			SchedTime zeroTFromUserInput = inpTime - outWireLatency;
			// if outWireLatency does not fit into space until clock
			// end, it should move to prev clk end + ffdelay +
			// outWireLatency
			assert(inpTime >= zeroTFromUserInput);
			zeroTFromUserInput = HlsNetNode::schedulerJumpToPrevCycleIfRequired(
				inpTime, zeroTFromUserInput, clkPeriod,
				ffdelay + outWireLatency);

			nodeZeroTime = std::min(nodeZeroTime, zeroTFromUserInput);
		}
		{
			HlsNetNodeWithMaxTimeRAII maxTimeOverride(*node, _endOfLastClk);
			nodeZeroTime = node->_scheduledZeroApplyLimits(nodeZeroTime, true, false);
			for (HlsNetNode *_ :
				 node->scheduleAlapCompactionUpdateFromInputDelays(
					 nodeZeroTime, endOfLastClk)) {
				// consume all items from generator (OutUserCount is used
				// instead of placing this items to worklist)
			}

			// :note: can not use scheduleAlapCompaction because the successors
			// connected to outputs of node may be entirely different graph from
			// edges_fw/bw
			// auto predNodes = node->scheduleAlapCompaction(_endOfLastClk);
			// for (auto *_ : predNodes) {
			//}
		}
		assert(node->scheduledZero.has_value());
		auto t = node->scheduledZero.value();
		// :note: reset the delay because the node may be part of multiple LUTs
		//if (node->_outputs.empty()) {
			if (!isPrimaryOutput)
				std::fill(node->inputWireDelay.begin(), node->inputWireDelay.end(),
						  0);
			//t -= lutDelay;
		//} else {
		//	std::fill(node->outputWireDelay.begin(),
		//			  node->outputWireDelay.end(), 0);
		//}

		node->scheduledZero = {};
		node->_setScheduleZeroTimeSingleClock(t);
		// Decrement indegree for every predecessor, once it falls to 0, it
		// means that all uses  predecessors by decrementing their indegree
		auto preds = edges_bw.find(node);
		if (preds != edges_bw.end()) {
			for (auto *pred : preds->second) {
				if (!nodes.contains(pred))
					continue;
				// std::cout << "getOutUserCount(*pred): " << pred->__repr__()
				// 	  << " -> " << node->__repr__() << " "
				// 	  << getOutUserCount(*pred) << std::endl;
				assert(getOutUserCount(*pred) > 0);
				if (--getOutUserCount(*pred) == 0) {
					readyNodes.push(pred);
				}
			}
		}
	}
	HlsNetNode::scratchpadClear(nodes);
	scheduleLutAlapCopySchedulingFromLutRepresentatorsToRestOfNodes(
		fmw, lutDelay, endOfLastClk);

}

} // namespace hwtHls::techmap