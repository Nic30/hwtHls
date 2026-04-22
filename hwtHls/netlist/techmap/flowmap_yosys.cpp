#include <algorithm>
#include <hwtHls/netlist/techmap/flowmap_yosys.h>
#include <hwtHls/netlist/techmap/hlsNetlist.h>

#include <assert.h>
#include <climits>
#include <ranges>
#include <stdexcept>
#include <vector>

#include <hwtHls/netlist/techmap/schedulingAlap.h>

// https://github.com/YosysHQ/yosys/blob/main/guidelines/GettingStarted
// https://github.com/YosysHQ/yosys/blob/main/kernel/hashlib.h

using namespace hwtHls;
using namespace std;

#define log(x...)
#define log_error(x...)
#define log_signal(x...) ""
#define log_assert(x) assert(x)

namespace hwtHls::techmap {

struct NodePrime {
	HlsNetNode *node;
	bool is_bottom;

	NodePrime(HlsNetNode *node, bool is_bottom) :
		node(node), is_bottom(is_bottom) {}

	bool operator==(const NodePrime &other) const {
		return node == other.node && is_bottom == other.is_bottom;
	}
	bool operator!=(const NodePrime &other) const { return !(*this == other); }

	static NodePrime top(HlsNetNode *node) {
		return NodePrime(node, /*is_bottom=*/false);
	}

	static NodePrime bottom(HlsNetNode *node) {
		return NodePrime(node, /*is_bottom=*/true);
	}

	NodePrime as_top() const {
		log_assert(is_bottom);
		return top(node);
	}

	NodePrime as_bottom() const {
		log_assert(!is_bottom);
		return bottom(node);
	}
};
} // namespace hwtHls::techmap

namespace std {
template <> struct hash<hwtHls::techmap::NodePrime> {
	std::size_t operator()(hwtHls::techmap::NodePrime const &s) const noexcept {
		size_t h1 = hash<hwtHls::HlsNetNode *>{}(s.node);
		size_t h2 = hash<bool>{}(s.is_bottom);
		return h1 ^ (h2 << 1);
	}
};
} // namespace std

namespace hwtHls::techmap {

bool FlowGraph::find_augmenting_path(bool commit) {
	NodePrime source_prime = {source, true};
	NodePrime sink_prime = {sink, false};
	vector<NodePrime> path = {source_prime};
	std::unordered_set<NodePrime> visited;
	bool found;
	do {
		found = false;

		auto node_prime = path.back();
		visited.insert(node_prime);

		if (!node_prime.is_bottom) { // vt
			if (!visited.contains(node_prime.as_bottom()) &&
				node_flow[node_prime.node] < MAX_NODE_FLOW) {
				path.push_back(node_prime.as_bottom());
				found = true;
			} else {
				for (HlsNetNode *node_pred : edges_bw[node_prime.node]) {
					if (!visited.contains(NodePrime::bottom(node_pred)) &&
						edge_flow[{node_pred, node_prime.node}] > 0) {
						path.push_back(NodePrime::bottom(node_pred));
						found = true;
						break;
					}
				}
			}
		} else { // vb
			if (!visited.contains(node_prime.as_top()) &&
				node_flow[node_prime.node] > 0) {
				path.push_back(node_prime.as_top());
				found = true;
			} else {
				for (HlsNetNode *node_succ : edges_fw[node_prime.node]) {
					if (!visited.contains(NodePrime::top(
							node_succ)) /* && edge_flow[...] < ∞ */) {
						path.push_back(NodePrime::top(node_succ));
						found = true;
						break;
					}
				}
			}
		}

		if (!found && path.size() > 1) {
			path.pop_back();
			found = true;
		}
	} while (path.back() != sink_prime && found);

	if (commit && path.back() == sink_prime) {
		auto prev_prime = path.front();
		for (auto node_prime : path) {
			if (node_prime == source_prime)
				continue;

			log_assert(prev_prime.is_bottom ^ node_prime.is_bottom);
			if (prev_prime.node == node_prime.node) {
				auto node = node_prime.node;
				if (!prev_prime.is_bottom && node_prime.is_bottom) {
					log_assert(node_flow[node] == 0);
					node_flow[node]++;
				} else {
					log_assert(node_flow[node] != 0);
					node_flow[node]--;
				}
			} else {
				if (prev_prime.is_bottom && !node_prime.is_bottom) {
					log_assert(true /* edge_flow[...] < ∞ */);
					edge_flow[{prev_prime.node, node_prime.node}]++;
				} else {
					log_assert(
						(edge_flow[{node_prime.node, prev_prime.node}] > 0));
					edge_flow[{node_prime.node, prev_prime.node}]--;
				}
			}
			prev_prime = node_prime;
		}

		node_flow[source]++;
		node_flow[sink]++;
	}
	return path.back() == sink_prime;
}

int FlowGraph::maximum_flow(int order) {
	int flow = 0;
	while (flow < order && find_augmenting_path(/*commit=*/true))
		flow++;
	return flow + find_augmenting_path(/*commit=*/false);
}

pair<pool<HlsNetNode *>, pool<HlsNetNode *>> FlowGraph::edge_cut() {
	pool<HlsNetNode *> x = {source}, xi; // X and X̅ in the paper

	NodePrime source_prime = {source, true};
	unordered_set<NodePrime> visited;
	vector<NodePrime> worklist = {source_prime};
	while (!worklist.empty()) {
		auto node_prime = worklist.back();
		worklist.pop_back();
		if (visited.contains(node_prime))
			continue;
		visited.insert(node_prime);

		if (!node_prime.is_bottom)
			x.insert(node_prime.node);

		// Mincut is constructed by traversing a graph in an undirected way
		// along forward edges that aren't full, or backward edges that aren't
		// empty.
		if (!node_prime.is_bottom) // top
		{
			if (node_flow[node_prime.node] < MAX_NODE_FLOW)
				worklist.push_back(node_prime.as_bottom());
			for (HlsNetNode *node_pred : edges_bw[node_prime.node])
				if (edge_flow[{node_pred, node_prime.node}] > 0)
					worklist.push_back(NodePrime::bottom(node_pred));
		} else // bottom
		{
			if (node_flow[node_prime.node] > 0)
				worklist.push_back(node_prime.as_top());
			for (HlsNetNode *node_succ : edges_fw[node_prime.node])
				if (true /* edge_flow[...] < ∞ */)
					worklist.push_back(NodePrime::top(node_succ));
		}
	}

	for (HlsNetNode *node : nodes)
		if (!x.contains(node))
			xi.insert(node);

	for (HlsNetNode *collapsed_node : collapsed[sink])
		xi.insert(collapsed_node);

	log_assert(x.contains(source) && !xi.contains(source));
	log_assert(!x.contains(sink) && xi.contains(sink));
	return {x, xi};
}

pool<HlsNetNode *> FlowmapWorker::find_subgraph(HlsNetNode *sink) {
	pool<HlsNetNode *> subgraph;
	pool<HlsNetNode *> worklist = {sink};
	while (!worklist.empty()) {
		HlsNetNode *node = worklist.pop();
		subgraph.insert(node);
		for (HlsNetNode *source : edges_bw[node]) {
			if (!subgraph.contains(source))
				worklist.insert(source);
		}
	}
	return subgraph;
}

FlowGraph FlowmapWorker::build_flow_graph(HlsNetNode *sink, int p) {
	FlowGraph flow_graph;
	flow_graph.sink = sink;

	pool<HlsNetNode *> worklist = {sink}, visited;
	while (!worklist.empty()) {
		HlsNetNode *node = worklist.pop();
		visited.insert(node);

		auto collapsed_node = labels[node] == p ? sink : node;
		if (node != collapsed_node)
			flow_graph.collapsed[collapsed_node].insert(node);
		flow_graph.nodes.insert(collapsed_node);

		for (HlsNetNode *node_pred : edges_bw[node]) {
			auto collapsed_node_pred =
				labels[node_pred] == p ? sink : node_pred;
			if (node_pred != collapsed_node_pred)
				flow_graph.collapsed[collapsed_node_pred].insert(node_pred);
			if (collapsed_node != collapsed_node_pred) {
				flow_graph.edges_bw[collapsed_node].insert(collapsed_node_pred);
				flow_graph.edges_fw[collapsed_node_pred].insert(collapsed_node);
			}
			if (inputs.contains(node_pred)) {
				flow_graph.edges_bw[collapsed_node_pred].insert(
					flow_graph.source);
				flow_graph.edges_fw[flow_graph.source].insert(
					collapsed_node_pred);
			}

			if (!visited.contains(node_pred))
				worklist.insert(node_pred);
		}
	}
	return flow_graph;
}

void FlowmapWorker::label_nodes() {
	for (auto* node : nodes) {
		labels[node] = -1;
		if (node->_inputs.size() > (size_t)order) {
			throw std::runtime_error(
				"FlowmapWorker: the node has more inputs than LUT, it needs to "
				"be lowered before " +
				node->__repr__());
		}
	}
	for (auto input : inputs) {
		// if (input.wire->attributes.count(ID($flowmap_level)))
		//	labels[input] = input.wire->attributes[ID($flowmap_level)].as_int();
		// else
		labels[input] = 0;
	}
	pool<HlsNetNode *> worklist(nodes);
	int debug_num = 0;
	while (!worklist.empty()) {
		HlsNetNode *sink = worklist.pop();
		if (labels[sink] != -1)
			continue;

		bool inputs_have_labels = true;
		for (auto sink_input : edges_bw[sink]) {
			if (labels[sink_input] == -1) {
				inputs_have_labels = false;
				break;
			}
		}
		if (!inputs_have_labels)
			continue;

		if (debug) {
			debug_num++;
			log("Examining subgraph %d rooted in %s.\n", debug_num,
				log_signal(sink));
		}

		pool<HlsNetNode *> subgraph = find_subgraph(sink);

		int p = 1;
		for (auto subgraph_node : subgraph)
			p = std::max<int>(p, labels[subgraph_node]);

		FlowGraph flow_graph = build_flow_graph(sink, p);
		int flow = flow_graph.maximum_flow(order);
		pool<HlsNetNode *> x, xi;
		if (flow <= order) {
			labels[sink] = p;
			auto cut = flow_graph.edge_cut();
			x = cut.first;
			xi = cut.second;
		} else {
			labels[sink] = p + 1;
			x = subgraph;
			x.erase(sink);
			xi.insert(sink);
		}
		lut_gates[sink] = xi;

		pool<HlsNetNode *> k;
		for (auto xi_node : xi) {
			for (HlsNetNode *xi_node_pred : edges_bw[xi_node])
				if (x.contains(xi_node_pred))
					k.insert(xi_node_pred);
		}
		log_assert((int)k.size() <= order);
		lut_edges_bw[sink] = k;
		for (HlsNetNode *k_node : k)
			lut_edges_fw[k_node].insert(sink);

		// if (debug)
		//{
		//	log("  Maximum flow: %d. Assigned label %d.\n", flow, labels[sink]);
		//	dump_dot_graph(stringf("flowmap-%d-sub.dot", debug_num),
		// GraphMode::Cut, subgraph, {}, {}, {x, xi}); 	log("  Dumped subgraph
		// to `flowmap-%d-sub.dot`.\n", debug_num);
		//	flow_graph.dump_dot_graph(stringf("flowmap-%d-flow.dot",
		// debug_num)); 	log("  Dumped flow graph to
		// `flowmap-%d-flow.dot`.\n", debug_num); 	log("    LUT inputs:");
		// for (auto k_node : k) 		log(" %s", log_signal(k_node));
		// log(".\n"); 	log("    LUT packed gates:"); 	for (auto xi_node : xi)
		// log(" %s", log_signal(xi_node)); 	log(".\n");
		// }

		for (HlsNetNode *sink_succ : edges_fw[sink])
			worklist.insert(sink_succ);
	}

	// if (debug)
	//{
	//	dump_dot_graph("flowmap-labeled.dot", GraphMode::Label);
	//	log("Dumped labeled graph to `flowmap-labeled.dot`.\n");
	// }
}

void FlowmapWorker::map_luts() {
	// select LUT representator nodes based on what edges are left in
	// lut_edges_bw
	pool<HlsNetNode *> worklist = outputs;
	while (!worklist.empty()) {
		HlsNetNode *lut_node = worklist.pop();
		lut_nodes.insert(lut_node);
		for (HlsNetNode *input_node : lut_edges_bw[lut_node])
			if (!lut_nodes.contains(input_node) && !inputs.contains(input_node))
				worklist.insert(input_node);
	}

	// prune unused nodes from LUTs
	for (auto lut : lut_nodes) {
		auto lutGates = lut_gates.find(lut);
		if (lutGates == lut_gates.end())
			continue;

		auto &allGatesOfLut = lutGates->second;
		worklist = allGatesOfLut;

		while (!worklist.empty()) {
			HlsNetNode *gate_node = worklist.pop();
			auto users = gate_node->iterOutUserNodes();
			if (gate_node != lut &&
				!std::any_of(users.begin(), users.end(),
							 [&allGatesOfLut](HlsNetNode &user) {
								 return allGatesOfLut.contains(&user);
							 })) {
				for (HlsNetNode &dep : gate_node->iterInDepNodes()) {
					if (allGatesOfLut.contains(&dep)) {
						worklist.insert(&dep);
						assert(&dep != gate_node);
					}
				}
				assert(allGatesOfLut.contains(gate_node));
				allGatesOfLut.erase(gate_node);
			}
		}
	}

	// int depth = 0;
	// for (auto label : labels)
	//	depth = max(depth, label.second);
	// log("Mapped to %d LUTs with maximum depth %d.\n", GetSize(lut_nodes),
	//	depth);

	// if (debug)
	//{
	//	dump_dot_lut_graph("flowmap-mapped.dot", GraphMode::Label);
	//	log("Dumped mapped graph to `flowmap-mapped.dot`.\n");
	// }

	// return depth;
}

void FlowmapWorker::reset() {
	labels.clear();
	lut_nodes.clear();
	lut_gates.clear();
	lut_edges_fw.clear();
	lut_edges_bw.clear();
}

FlowmapWorker::FlowmapWorker(std::vector<HlsNetNode *> &nodes,
							 std::vector<HlsNetNode *> &inputs,
							 std::vector<HlsNetNode *> &outputs, int order,
							 int minlut, bool debug) :
	order(order),
	debug(debug),
	nodes(nodes),
	inputs(inputs),
	outputs(outputs),
	edges_fw() {

	for (HlsNetNode *src : nodes) {
		if (this->outputs.contains(src))
			continue;
		auto sucList = edges_fw.find(src);
		if (sucList == edges_fw.end()) {
			edges_fw[src] = {};
			sucList = edges_fw.find(src);
		}
		for (HlsNetNode &dst : src->iterOutUserNodes()) {
			if (!this->nodes.contains(&dst))
				continue;
			sucList->second.insert(&dst);
		}
	}
	for (auto kv : edges_fw) {
		for (auto *dst : kv.second) {
			auto preds = edges_bw.find(dst);
			if (preds != edges_bw.end()) {
				preds->second.insert(kv.first);
			} else {
				edges_bw[dst] = {kv.first};
			}
		}
	}
}

//	log("Labeling cells.\n");
//// discover_nodes(cell_types);
//	    label_nodes();
//	    int depth = map_luts();
//
//	if (relax)
//	{
//		log("\n");
//		log("Optimizing area.\n");
//		optimize_area(depth, optarea);
//	}
//
//	log("\n");
//	log("Packing cells.\n");
//	pack_cells(minlut);
//}

} // namespace hwtHls::techmap
