#include <hwtHls/netlist/techmap/schedulingAlap.h>

#include <algorithm>
#include <assert.h>
#include <queue>
#include <vector>

#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/pool.h>

namespace hwtHls::techmap {


void resetSchedule(const pool<HlsNetNode *> &nodes) {
	for (auto *node : nodes) {
		node->scheduledZero = std::nullopt;
		std::fill(node->scheduledIn.begin(), node->scheduledIn.end(), 0);
		std::fill(node->scheduledOut.begin(), node->scheduledOut.end(), 0);
		assert(node->_scratchpad == nullptr &&
			   "Scratchpad should be clean before call of this function");
	}
}

void alapSchedule(const pool<HlsNetNode *> &nodes, SchedTime maxLatency) {
	// resetSchedule(nodes);

	// Kahn's algorithm for reverse topological order (sinks first)
	// Initialize indegrees: count outputs with users
	std::queue<HlsNetNode *> ready;
	for (auto *node : nodes) {
		OutUserCounter indeg = 0;
		for (const auto &outList : node->usedBy) {
			indeg += outList.size();
		}
		getOutUserCount(*node) = indeg;
		if (indeg == 0)
			ready.push(node);
	}

	while (!ready.empty()) {
		HlsNetNode *node = ready.front();
		ready.pop();
		assert(!node->scheduledZero.has_value());
		// Compute scheduleOut: min over all users' scheduleIn - 1
		for (size_t o = 0; o < node->_outputs.size(); ++o) {
			SchedTime minOutTime = maxLatency;
			for (const auto &userIn : node->usedBy[o]) {
				minOutTime =
					std::min(minOutTime, userIn.obj->scheduledIn[userIn.in_i]);
			}
			node->scheduledOut[o] = minOutTime - node->outputWireDelay[o];
		}

		// Compute scheduleIn from predecessors' scheduleOut
		for (size_t i = 0; i < node->_inputs.size(); ++i) {
			auto &dep = node->dependsOn[i];
			assert(dep.has_value() &&
				   "Port must be connected before scheduling");
			node->scheduledIn[i] = dep->obj->scheduledOut[dep->out_i];
		}

		// Execution time = max input arrival
		if (!node->scheduledIn.empty()) {
			node->scheduledZero = *std::max_element(node->scheduledIn.begin(),
													node->scheduledIn.end());
		}

		// Decrement indegree for every predecessor, once it falls to 0, it
		// means that all uses  predecessors by decrementing their indegree
		for (size_t i = 0; i < node->_inputs.size(); ++i) {
			auto &dep = node->dependsOn[i];
			assert(dep.has_value() &&
				   "Port must be connected before scheduling");
			HlsNetNode *pred = dep->obj;
			if (--getOutUserCount(*pred) == 0) {
				ready.push(pred);
			}
		}
	}
#ifndef NDEBUG
	for (auto *node : nodes) {
		assert(getOutUserCount(*node) == 0 && "All nodes scheduled");
	}
#endif
	HlsNetNode::scratchpadClear(nodes);
}

} // namespace hwtHls::techmap
