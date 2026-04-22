#pragma once
// this file is practically copied https://github.com/YosysHQ/yosys/blob/main/passes/techmap/flowmap.cc modified for custom node types

#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <hwtHls/netlist/techmap/pool.h>
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/flowmap_yosys.h>

namespace hwtHls::techmap {

class FlowmapAreaOpt {
public:
	int order;
	int r_alpha, r_beta, r_gamma;
	bool debug_relax;

	// Gate IR
	pool<HlsNetNode*> &nodes, &inputs, &outputs;
	// :note: edges_fw/edges_bw is used instead of port connections from legacy reasons (the yosys implementation is using them
	//   and we want to have be able to diff changes with yosys version easily)
	std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &edges_fw, &edges_bw;
	// :note: label corresponds to a depth of the node in graph
	std::unordered_map<HlsNetNode*, int> &labels;

	// LUT IR
	pool<HlsNetNode*> &lut_nodes; // original nodes picked to represent LUT (which are the out of LUT)
	std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_gates;
	std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_edges_fw,
			&lut_edges_bw;

	// LUT depth is the length of the longest path from any input in LUT fan-in to LUT.
	// LUT altitude (for lack of a better term) is the length of the longest path from LUT to any output in LUT fan-out.
	std::unordered_map<HlsNetNode*, int> lut_depths, lut_altitudes, lut_slacks;

	FlowmapAreaOpt(FlowmapWorker &fmw, int r_alpha = 8, int r_beta = 2,
			int r_gamma = 1, bool debug_relax = false);

protected:
	void realize_derealize_lut(HlsNetNode *lut, pool<HlsNetNode*> *changed =
			nullptr);

	void add_lut_edge(HlsNetNode *pred, HlsNetNode *succ,
			pool<HlsNetNode*> *changed = nullptr);
	void remove_lut_edge(HlsNetNode *pred, HlsNetNode *succ,
			pool<HlsNetNode*> *changed = nullptr);

	std::pair<pool<HlsNetNode*>, pool<HlsNetNode*>> cut_lut_at_gate(
			HlsNetNode *lut, HlsNetNode *lut_gate);
	void compute_lut_distances(
			std::unordered_map<HlsNetNode*, int> &lut_distances, bool forward,
			pool<HlsNetNode*> initial = { }, pool<HlsNetNode*> *changed =
					nullptr);
	void check_lut_distances(
			const std::unordered_map<HlsNetNode*, int> &lut_distances,
			bool forward);

	// LUT depth is the length of the longest path from any input in LUT fan-in to LUT.
	// LUT altitude (for lack of a better term) is the length of the longest path from LUT to any output in LUT fan-out.
	void update_lut_depths_altitudes(pool<HlsNetNode*> worklist = { },
			pool<HlsNetNode*> *changed = nullptr);
	// LUT critical output set is the set of outputs whose depth will increase (equivalently, slack will decrease) if the depth of
	// the LUT increases. (This is referred to as RPOv for LUTv in the paper.)
	void compute_lut_critical_outputs(
			std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
			pool<HlsNetNode*> worklist = { });
	// Invalidating LUT critical output sets is tricky, because increasing the depth of a LUT may take other, adjacent LUTs off the critical
	// path to the output. Conservatively, if we increase depth of some LUT, every LUT in its input cone needs to have its critical output
	// set invalidated, too.
	pool<HlsNetNode*> invalidate_lut_critical_outputs(
			std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
			pool<HlsNetNode*> worklist);

	void check_lut_critical_outputs(
			const std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs);

	void update_lut_critical_outputs(
			std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
			pool<HlsNetNode*> worklist = { });

	void update_breaking_node_potentials(
			std::unordered_map<HlsNetNode*, std::unordered_map<HlsNetNode*, int>> &potentials,
			const std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs);
	bool relax_depth_for_bound(bool first, int depth_bound,
			std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs);
public:
	// :note: "main"
	void optimize_area(int depth, int optarea);
};

}
