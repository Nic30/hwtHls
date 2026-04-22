#pragma once
// this file is practically copied
// https://github.com/YosysHQ/yosys/blob/main/passes/techmap/flowmap.cc modified
// for custom node types
/*
 *  yosys -- Yosys Open SYnthesis Suite
 *
 *  Copyright (C) 2018  whitequark <whitequark@whitequark.org>
 *
 *  Permission to use, copy, modify, and/or distribute this software for any
 *  purpose with or without fee is hereby granted, provided that the above
 *  copyright notice and this permission notice appear in all copies.
 *
 *  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
 *  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
 *  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
 *  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
 *  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
 *  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
 *  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
 *
 */

// [[CITE]] FlowMap algorithm
// Jason Cong; Yuzheng Ding, "An Optimal Technology Mapping Algorithm for Delay
// Optimization in Lookup-Table Based FPGA Designs," Computer-Aided Design of
// Integrated Circuits and Systems, IEEE Transactions on, Vol. 13, pp. 1-12,
// Jan. 1994. doi: 10.1109/43.273754
// [[CITE]] FlowMap-r algorithm
// Jason Cong; Yuzheng Ding, "On Area/Depth Tradeoff in LUT-Based FPGA
// Technology Mapping," Very Large Scale Integration Systems, IEEE Transactions
// on, Vol. 2, June 1994. doi: 10.1109/92.28574 Required reading material:
//
// Min-cut max-flow theorem:
//   https://www.coursera.org/lecture/algorithms-part2/maxflow-mincut-theorem-beb9G
// FlowMap paper:
//   http://cadlab.cs.ucla.edu/~cong/papers/iccad92.pdf   (short version)
//   https://limsk.ece.gatech.edu/book/papers/flowmap.pdf (long version)
// FlowMap-r paper:
//   http://cadlab.cs.ucla.edu/~cong/papers/dac93.pdf     (short version)
//   https://sci-hub.tw/10.1109/92.285741                 (long version)
// Notes on correspondence between paper and implementation:
//
// 1. In the FlowMap paper, the nodes are logic elements (analogous to Yosys
// cells) and edges are wires. However, in our implementation, we use an
// inverted approach: the nodes are Yosys wire bits, and the edges are derived
// from (but aren't represented by) Yosys cells. This may seem counterintuitive.
// Three observations may help understanding this. First, for a cell with a
// 1-bit Y output that is the sole driver of its output net (which is the
// typical case), these representations are equivalent, because there is an
// exact correspondence between cells and output wires. Second, in the paper,
// primary inputs (analogous to Yosys cell or module ports) are nodes, and in
// Yosys, inputs are wires; our approach allows a direct mapping from both
// primary inputs and 1-output logic elements to flow graph nodes. Third, Yosys
// cells may have multiple outputs or multi-bit outputs, and by using Yosys wire
// bits as flow graph nodes, such cells are supported without any additional
// effort; any Yosys cell with n output wire bits ends up being split into n
// flow graph nodes.
//
// 2. The FlowMap paper introduces three networks: Nt, Nt', and Nt''. The
// network Nt is directly represented by a subgraph of RTLIL graph, which is
// parsed into an equivalent but easier to traverse representation in
// FlowmapWorker. The network Nt' is built explicitly from a subgraph of Nt, and
// uses a similar representation in FlowGraph. The network Nt'' is implicit in
// FlowGraph, which is possible because of the following observation: each Nt'
// node corresponds to an Nt'' edge of capacity 1, and each Nt' edge corresponds
// to an Nt'' edge of capacity ∞. Therefore, we only need to explicitly record
// flow for Nt' edges and through Nt' nodes.
//
// 3. The FlowMap paper ambiguously states: "Moreover, we can find such a cut
// (X′′, X̅′′) by performing a depth first search starting at the source s, and
// including in X′′ all the nodes which are reachable from s." This actually
// refers to a specific kind of search, min-cut computation. Min-cut computation
// involves computing the set of nodes reachable from s by an undirected path
// with no full (i.e. zero capacity) forward edges or empty (i.e. no flow)
// backward edges. In addition, the depth first search is required to compute a
// max-volume max-flow min-cut specifically, because a max-flow min-cut is not,
// in general, unique. Notes on implementation:
//
// 1. To compute depth optimal packing, an intermediate representation is used,
// where each cell with n output bits is split into n graph nodes. Each such
// graph node is represented directly with the wire bit (HlsNetNode* instance)
// that corresponds to the output bit it is created from. Fan-in and fan-out are
// represented explicitly by edge lists derived from the RTLIL graph. This IR
// never changes after it has been computed.
//
// In terms of data, this IR is comprised of `inputs`, `outputs`, `nodes`,
// `edges_fw` and `edges_bw` fields.
//
// We call this IR "gate IR".
//
// 2. To compute area optimal packing, another intermediate representation is
// used, which consists of some K-feasible cone for every node that exists in
// the gate IR. Immediately after depth optimal packing with FlowMap, each such
// cone occupies the lowest possible depth, but this is not true in general, and
// transformations of this IR may change the cones, although each transformation
// has to keep each cone K-feasible. In this IR, LUT fan-in and fan-out are
// represented explicitly by edge lists; if a K-feasible cone chosen for node A
// includes nodes B and C, there are edges between all predecessors of A, B and
// C in the gate IR and node A in this IR. Moreover, in this IR, cones may be
// *realized* or *derealized*. Only realized cones will end up mapped to actual
// LUTs in the output of this pass.
//
// Intuitively, this IR contains (some, ideally but not necessarily optimal) LUT
// representation for each input cell. By starting at outputs and traversing the
// graph of this IR backwards, each K-feasible cone is converted to an actual
// LUT at the end of the pass. This is the same as iterating through each
// realized LUT.
//
// The following are the invariants of this IR:
//   a) Each gate IR node corresponds to a K-feasible cut.
//   b) Each realized LUT is reachable through backward edges from some output.
//   c) The LUT fan-in is exactly the fan-in of its constituent gates minus the
//   fan-out of its constituent gates.
// The invariants are kept even for derealized LUTs, since the whole point of
// this IR is ease of packing, unpacking, and repacking LUTs.
//
// In terms of data, this IR is comprised of `lut_nodes` (the set of all
// realized LUTs), `lut_gates` (the map from a LUT to its constituent gates),
// `lut_edges_fw` and `lut_edges_bw` fields. The `inputs` and `outputs` fields
// are shared with the gate IR.
//
// We call this IR "LUT IR".
#include <hwtHls/netlist/techmap/hlsNetlist.h>
#include <hwtHls/netlist/techmap/pool.h>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace hwtHls::techmap {

struct FlowGraph {
	HlsNetNode *source = nullptr;
	HlsNetNode *sink;
	pool<HlsNetNode *> nodes = {source};
	std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> edges_fw, edges_bw;

	const int MAX_NODE_FLOW = 1;
	std::unordered_map<HlsNetNode *, int> node_flow;
	std::unordered_map<std::pair<HlsNetNode *, HlsNetNode *>, int> edge_flow;

	std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> collapsed;

	// Here, we are working on the Nt'' network, but our representation is the
	// Nt' network. The difference between these is that where in Nt' we have a
	// subgraph:
	//
	//   v1 -> v2 -> v3
	//
	// in Nt'' we have a corresponding subgraph:
	//
	//   v'1b -∞-> v'2t -f-> v'2b -∞-> v'3t
	//
	// To address this, we split each node v into two nodes, v't and v'b. This
	// representation is virtual, in the sense that nodes v't and v'b are
	// overlaid on top of the original node v, and only exist in paths and
	// worklists.

	bool find_augmenting_path(bool commit);

	int maximum_flow(int order);

	std::pair<pool<HlsNetNode *>, pool<HlsNetNode *>> edge_cut();
};

struct FlowmapWorker {
	int order;
	bool debug;

	// Gate IR
	pool<HlsNetNode *> nodes, inputs, outputs;
	// :note: edges_fw/edges_bw is used instead of port connections from legacy
	// reasons (the yosys implementation is using them
	//   and we want to have be able to diff changes with yosys version easily)
	std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> edges_fw, edges_bw;
	// :note: label corresponds to a depth of the node in graph
	std::unordered_map<HlsNetNode *, int> labels;

	// LUT IR
	pool<HlsNetNode *> lut_nodes; // original nodes picked to represent LUT
								  // (which are the out of LUT)
	std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> lut_gates;
	std::unordered_map<HlsNetNode *, pool<HlsNetNode *>> lut_edges_fw,
		lut_edges_bw;

	// for a given sink node collect all predecessors recursively
	pool<HlsNetNode *> find_subgraph(HlsNetNode *sink);
	FlowGraph build_flow_graph(HlsNetNode *sink, int p);

	void label_nodes();
	void map_luts();

	// reinitialize FlowmapWorker for new mapping
	void reset();

	// :note: nodes should contain also nodes from inputs/outputs
	FlowmapWorker(std::vector<HlsNetNode *> &nodes,
				  std::vector<HlsNetNode *> &inputs,
				  std::vector<HlsNetNode *> &outputs, int order = 3,
				  int minlut = 1, bool debug = false);
};


} // namespace hwtHls::techmap
