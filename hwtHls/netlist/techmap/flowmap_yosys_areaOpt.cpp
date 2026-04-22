#include <hwtHls/netlist/techmap/flowmap_yosys_areaOpt.h>

using namespace std;
#define log(x ...)
#define log_error(x ...)
#define log_signal(x ...) ""
#define log_assert(x)	assert(x)

namespace hwtHls::techmap {

FlowmapAreaOpt::FlowmapAreaOpt(FlowmapWorker &fmw, int r_alpha, int r_beta,
		int r_gamma, bool debug_relax) :
		order(fmw.order),              //
		r_alpha(r_alpha),              //
		r_beta(r_beta),                //
		r_gamma(r_gamma),              //
		debug_relax(debug_relax),      //
		nodes(fmw.nodes),              //
		inputs(fmw.inputs),            //
		outputs(fmw.outputs),          //
		edges_fw(fmw.edges_fw),        //
		edges_bw(fmw.edges_bw),        //
		labels(fmw.labels),            //
		lut_nodes(fmw.lut_nodes),      //
		lut_gates(fmw.lut_gates),      //
		lut_edges_fw(fmw.lut_edges_fw),      //
		lut_edges_bw(fmw.lut_edges_bw) //
{
}
void FlowmapAreaOpt::realize_derealize_lut(HlsNetNode *lut,
		pool<HlsNetNode*> *changed) {
	pool<HlsNetNode*> worklist = { lut };
	while (!worklist.empty()) {
		HlsNetNode *lut = worklist.pop();
		if (inputs.contains(lut))
			continue;

		bool realized_successors = false;
		for (auto lut_succ : lut_edges_fw[lut])
			if (lut_nodes.contains(lut_succ))
				realized_successors = true;

		if (realized_successors && !lut_nodes.contains(lut))
			lut_nodes.insert(lut);
		else if (!realized_successors && lut_nodes.contains(lut))
			lut_nodes.erase(lut);
		else
			continue;

		for (auto &lut_pred : lut_edges_bw[lut])
			worklist.insert(lut_pred);

		if (changed)
			changed->insert(lut);
	}
}

void FlowmapAreaOpt::add_lut_edge(HlsNetNode *pred, HlsNetNode *succ,
		pool<HlsNetNode*> *changed) {
	log_assert(
			!lut_edges_fw[pred].contains(succ)
					&& !lut_edges_bw[succ].contains(pred));
	log_assert((int ) lut_edges_bw[succ].size() < order);

	lut_edges_fw[pred].insert(succ);
	lut_edges_bw[succ].insert(pred);
	realize_derealize_lut(pred, changed);

	if (changed) {
		changed->insert(pred);
		changed->insert(succ);
	}
}

void FlowmapAreaOpt::remove_lut_edge(HlsNetNode *pred, HlsNetNode *succ,
		pool<HlsNetNode*> *changed) {
	log_assert(
			lut_edges_fw[pred].contains(succ)
					&& lut_edges_bw[succ].contains(pred));

	lut_edges_fw[pred].erase(succ);
	lut_edges_bw[succ].erase(pred);
	realize_derealize_lut(pred, changed);

	if (changed) {
		if (lut_nodes.contains(pred))
			changed->insert(pred);
		changed->insert(succ);
	}
}

void FlowmapAreaOpt::compute_lut_distances(
		std::unordered_map<HlsNetNode*, int> &lut_distances, bool forward,
		pool<HlsNetNode*> initial, pool<HlsNetNode*> *changed) {
	pool<HlsNetNode*> terminals = forward ? inputs : outputs;
	auto &lut_edges_next = forward ? lut_edges_fw : lut_edges_bw;
	auto &lut_edges_prev = forward ? lut_edges_bw : lut_edges_fw;

	if (initial.empty())
		initial = terminals;
	for (HlsNetNode *node : initial)
		lut_distances.erase(node);

	pool<HlsNetNode*> worklist = initial;
	while (!worklist.empty()) {
		HlsNetNode *lut = worklist.pop();
		int lut_distance = 0;
		if (forward && inputs.contains(lut))
			lut_distance = labels[lut]; // to support (* $flowmap_level=n *)
		for (auto lut_prev : lut_edges_prev[lut])
			if ((lut_nodes.contains(lut_prev) || inputs.contains(lut_prev))
					&& lut_distances.count(lut_prev))
				lut_distance = max(lut_distance, lut_distances[lut_prev] + 1);
		if (!lut_distances.count(lut) || lut_distances[lut] != lut_distance) {
			lut_distances[lut] = lut_distance;
			if (changed != nullptr && !inputs.contains(lut))
				changed->insert(lut);
			for (HlsNetNode *lut_next : lut_edges_next[lut])
				if (lut_nodes.contains(lut_next) || inputs.contains(lut_next))
					worklist.insert(lut_next);
		}
	}
}

void FlowmapAreaOpt::check_lut_distances(
		const std::unordered_map<HlsNetNode*, int> &lut_distances,
		bool forward) {
	std::unordered_map<HlsNetNode*, int> gold_lut_distances;
	compute_lut_distances(gold_lut_distances, forward);
	for (auto lut_distance : lut_distances)
		if (lut_nodes.contains(lut_distance.first))
			log_assert(
					lut_distance.second
							== gold_lut_distances[lut_distance.first]);
}

void FlowmapAreaOpt::optimize_area(int depth, int optarea) {
	std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> lut_critical_outputs;
	update_lut_depths_altitudes();
	update_lut_critical_outputs(lut_critical_outputs);

	for (int depth_bound = depth; depth_bound <= depth + optarea;
			depth_bound++) {
		log("Relaxing with depth bound %d.\n", depth_bound);
		bool fully_relaxed = relax_depth_for_bound(depth_bound == depth,
				depth_bound, lut_critical_outputs);

		if (fully_relaxed)
			break;
	}
}

// LUT depth is the length of the longest path from any input in LUT fan-in to LUT.
// LUT altitude (for lack of a better term) is the length of the longest path from LUT to any output in LUT fan-out.
void FlowmapAreaOpt::update_lut_depths_altitudes(pool<HlsNetNode*> worklist,
		pool<HlsNetNode*> *changed) {
	compute_lut_distances(lut_depths, /*forward=*/true, worklist, changed);
	compute_lut_distances(lut_altitudes, /*forward=*/false, worklist, changed);
	if (debug_relax && !worklist.empty()) {
		check_lut_distances(lut_depths, /*forward=*/true);
		check_lut_distances(lut_altitudes, /*forward=*/false);
	}
}

bool FlowmapAreaOpt::relax_depth_for_bound(bool first, int depth_bound,
		std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs) {
	// int initial_count = lut_nodes.size();

	for (auto node : lut_nodes) {
		lut_slacks[node] = depth_bound
				- (lut_depths[node] + lut_altitudes[node]);
		log_assert(lut_slacks[node] >= 0);
	}
	//if (debug)
	//{
	//	dump_dot_lut_graph(stringf("flowmap-relax-%d-initial.dot", depth_bound), GraphMode::Slack);
	//	log("  Dumped initial slack graph to `flowmap-relax-%d-initial.dot`.\n", depth_bound);
	//}

	std::unordered_map<HlsNetNode*, std::unordered_map<HlsNetNode*, int>> potentials;
	for (int break_num = 1;; break_num++) {
		update_breaking_node_potentials(potentials, lut_critical_outputs);

		if (potentials.empty()) {
			log("  Relaxed to %d (+%d) LUTs.\n", GetSize(lut_nodes),
					GetSize(lut_nodes) - initial_count);
			if (!first && break_num == 1) {
				log("  Design fully relaxed.\n");
				return true;
			} else {
				log("  Slack exhausted.\n");
				break;
			}
		}

		HlsNetNode *breaking_lut, *breaking_gate;
		int best_potential = INT_MIN;
		for (auto lut_gate_potentials : potentials) {
			for (auto gate_potential : lut_gate_potentials.second) {
				if (gate_potential.second > best_potential) {
					breaking_lut = lut_gate_potentials.first;
					breaking_gate = gate_potential.first;
					best_potential = gate_potential.second;
				}
			}
		}log("  Breaking LUT %s to %s LUT %s (potential %d).\n",
				log_signal(breaking_lut),
				lut_nodes[breaking_gate] ? "reuse" : "extract",
				log_signal(breaking_gate), best_potential);

		if (debug_relax)
			log("    Removing breaking gate %s from LUT.\n",
					log_signal(breaking_gate));
		lut_gates[breaking_lut].erase(breaking_gate);

		auto cut_inputs = cut_lut_at_gate(breaking_lut, breaking_gate);
		pool<HlsNetNode*> gate_inputs = cut_inputs.first, other_inputs =
				cut_inputs.second;

		pool<HlsNetNode*> worklist = lut_gates[breaking_lut];
		pool<HlsNetNode*> elim_gates = gate_inputs;
		while (!worklist.empty()) {
			HlsNetNode *lut_gate = worklist.pop();
			bool all_gate_preds_elim = true;
			for (auto lut_gate_pred : edges_bw[lut_gate])
				if (!elim_gates.contains(lut_gate_pred))
					all_gate_preds_elim = false;
			if (all_gate_preds_elim) {
				if (debug_relax)
					log("    Removing gate %s from LUT.\n",
							log_signal(lut_gate));
				lut_gates[breaking_lut].erase(lut_gate);
				for (auto lut_gate_succ : edges_fw[lut_gate])
					worklist.insert(lut_gate_succ);
			}
		}
		log_assert(!lut_gates[breaking_lut].empty());

		pool<HlsNetNode*> directly_affected_nodes = { breaking_lut };
		for (auto gate_input : gate_inputs) {
			if (debug_relax)
				log("    Removing LUT edge %s -> %s.\n", log_signal(gate_input),
						log_signal(breaking_lut));
			remove_lut_edge(gate_input, breaking_lut, &directly_affected_nodes);
		}
		if (debug_relax)
			log("    Adding LUT edge %s -> %s.\n", log_signal(breaking_gate),
					log_signal(breaking_lut));
		add_lut_edge(breaking_gate, breaking_lut, &directly_affected_nodes);

		if (debug_relax)
			log("  Updating slack and potentials.\n");

		pool<HlsNetNode*> indirectly_affected_nodes = { };
		update_lut_depths_altitudes(directly_affected_nodes,
				&indirectly_affected_nodes);
		update_lut_critical_outputs(lut_critical_outputs,
				indirectly_affected_nodes);
		for (auto node : indirectly_affected_nodes) {
			lut_slacks[node] = depth_bound
					- (lut_depths[node] + lut_altitudes[node]);
			log_assert(lut_slacks[node] >= 0);
			if (debug_relax)
				log("    LUT %s now has depth %d and slack %d.\n",
						log_signal(node), lut_depths[node], lut_slacks[node]);
		}

		worklist = indirectly_affected_nodes;
		std::unordered_set<HlsNetNode*> visited;
		while (!worklist.empty()) {
			HlsNetNode *node = worklist.pop();
			visited.insert(node);
			potentials.erase(node);
			// We are invalidating the entire output cone of the gate IR node, not just of the LUT IR node. This is done to also invalidate
			// all LUTs that could contain one of the indirectly affected nodes as a *part* of them, as they may not be in the output cone
			// of any of the LUT IR nodes, e.g. if we have a LUT IR node A and node B as predecessors of node C, where node B includes all
			// gates from node A.
			for (auto node_succ : edges_fw[node])
				if (!visited.contains(node_succ))
					worklist.insert(node_succ);
		}

		//if (debug)
		//{
		//	dump_dot_lut_graph(stringf("flowmap-relax-%d-break-%d.dot", depth_bound, break_num), GraphMode::Slack);
		//	log("  Dumped slack graph after break %d to `flowmap-relax-%d-break-%d.dot`.\n",  break_num, depth_bound, break_num);
		//}
	}

	return false;
}

// LUT critical output set is the set of outputs whose depth will increase (equivalently, slack will decrease) if the depth of
// the LUT increases. (This is referred to as RPOv for LUTv in the paper.)
void FlowmapAreaOpt::compute_lut_critical_outputs(
		std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
		pool<HlsNetNode*> worklist) {
	if (worklist.empty())
		worklist = lut_nodes;

	while (!worklist.empty()) {
		bool updated_some = false;
		for (auto lut : worklist) {
			if (outputs.contains(lut))
				lut_critical_outputs[lut] = { lut };
			else {
				bool all_succ_computed = true;
				lut_critical_outputs[lut] = { };
				for (auto lut_succ : lut_edges_fw[lut]) {
					if (lut_nodes.contains(lut_succ)
							&& lut_depths[lut_succ] == lut_depths[lut] + 1) {
						if (lut_critical_outputs.count(lut_succ))
							lut_critical_outputs[lut].insert(
									lut_critical_outputs[lut_succ].begin(),
									lut_critical_outputs[lut_succ].end());
						else {
							all_succ_computed = false;
							break;
						}
					}
				}
				if (!all_succ_computed) {
					lut_critical_outputs.erase(lut);
					continue;
				}
			}
			worklist.erase(lut);
			updated_some = true;
		}
		log_assert(updated_some);
	}
}

// Invalidating LUT critical output sets is tricky, because increasing the depth of a LUT may take other, adjacent LUTs off the critical
// path to the output. Conservatively, if we increase depth of some LUT, every LUT in its input cone needs to have its critical output
// set invalidated, too.
pool<HlsNetNode*> FlowmapAreaOpt::invalidate_lut_critical_outputs(
		std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
		pool<HlsNetNode*> worklist) {
	pool<HlsNetNode*> changed;
	while (!worklist.empty()) {
		HlsNetNode *lut = worklist.pop();
		changed.insert(lut);
		lut_critical_outputs.erase(lut);
		for (auto lut_pred : lut_edges_bw[lut]) {
			if (lut_nodes.contains(lut_pred) && !changed.contains(lut_pred)) {
				changed.insert(lut_pred);
				worklist.insert(lut_pred);
			}
		}
	}
	return changed;
}

void FlowmapAreaOpt::check_lut_critical_outputs(
		const std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs) {
	std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> gold_lut_critical_outputs;
	compute_lut_critical_outputs(gold_lut_critical_outputs);
	for (auto lut_critical_output : lut_critical_outputs)
		if (lut_nodes.contains(lut_critical_output.first))
			log_assert(
					lut_critical_output.second
							== gold_lut_critical_outputs[lut_critical_output.first]);
}

void FlowmapAreaOpt::update_lut_critical_outputs(
		std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs,
		pool<HlsNetNode*> worklist) {
	if (!worklist.empty()) {
		pool<HlsNetNode*> invalidated = invalidate_lut_critical_outputs(
				lut_critical_outputs, worklist);
		compute_lut_critical_outputs(lut_critical_outputs, invalidated);
		check_lut_critical_outputs(lut_critical_outputs);
	} else
		compute_lut_critical_outputs(lut_critical_outputs);
}

void FlowmapAreaOpt::update_breaking_node_potentials(
		std::unordered_map<HlsNetNode*, std::unordered_map<HlsNetNode*, int>> &potentials,
		const std::unordered_map<HlsNetNode*, pool<HlsNetNode*>> &lut_critical_outputs) {
	for (HlsNetNode *lut : lut_nodes) {
		if (potentials.count(lut))
			continue;
		if (lut_gates[lut].size() == 1 || lut_slacks[lut] == 0)
			continue;

		if (debug_relax)
			log("  Computing potentials for LUT %s.\n", log_signal(lut));

		for (auto lut_gate : lut_gates[lut]) {
			if (lut == lut_gate)
				continue;

			if (debug_relax)
				log("    Considering breaking node %s.\n",
						log_signal(lut_gate));

			int r_ex, r_im, r_slk;

			auto cut_inputs = cut_lut_at_gate(lut, lut_gate);
			pool<HlsNetNode*> gate_inputs = cut_inputs.first, other_inputs =
					cut_inputs.second;
			if (gate_inputs.empty() && (int) other_inputs.size() >= order) {
				if (debug_relax)
					log("      Breaking would result in a (k+1)-LUT.\n");
				continue;
			}

			pool<HlsNetNode*> elim_fanin_luts;
			for (auto gate_input : gate_inputs) {
				if (lut_edges_fw[gate_input].size() == 1) {
					log_assert(lut_edges_fw[gate_input].contains(lut));
					elim_fanin_luts.insert(gate_input);
				}
			}
			//if (debug_relax) {
			//	if (!lut_nodes.contains(lut_gate))
			//		log("      Breaking requires a new LUT.\n");
			//	if (!gate_inputs.empty()) {
			//		log("      Breaking eliminates LUT inputs");
			//		for (auto gate_input : gate_inputs)
			//			log(" %s", log_signal(gate_input));log(".\n");
			//	}
			//	if (!elim_fanin_luts.empty()) {
			//		log("      Breaking eliminates fan-in LUTs");
			//		for (auto elim_fanin_lut : elim_fanin_luts)
			//			log(" %s", log_signal(elim_fanin_lut));log(".\n");
			//	}
			//}
			r_ex = (lut_nodes.contains(lut_gate) ? 0 : -1)
					+ elim_fanin_luts.size();

			pool<pair<HlsNetNode*, HlsNetNode*>> maybe_mergeable_luts;

			// Try to merge LUTv with one of its successors.
			HlsNetNode *last_lut_succ;
			int fanout = 0;
			for (auto lut_succ : lut_edges_fw[lut]) {
				if (lut_nodes.contains(lut_succ)) {
					fanout++;
					last_lut_succ = lut_succ;
				}
			}
			if (fanout == 1)
				maybe_mergeable_luts.insert(std::make_pair(lut, last_lut_succ));

			// Try to merge LUTv with one of its predecessors.
			for (auto lut_pred : other_inputs) {
				int fanout = 0;
				for (auto lut_pred_succ : lut_edges_fw[lut_pred])
					if (lut_nodes.contains(lut_pred_succ)
							|| lut_pred_succ == lut_gate)
						fanout++;
				if (fanout == 1)
					maybe_mergeable_luts.insert( { lut_pred, lut });
			}

			// Try to merge LUTw with one of its predecessors.
			for (auto lut_gate_pred : lut_edges_bw[lut_gate]) {
				int fanout = 0;
				for (auto lut_gate_pred_succ : lut_edges_fw[lut_gate_pred])
					if (lut_nodes.contains(lut_gate_pred_succ)
							|| lut_gate_pred_succ == lut_gate)
						fanout++;
				if (fanout == 1)
					maybe_mergeable_luts.insert( { lut_gate_pred, lut_gate });
			}

			r_im = 0;
			for (auto maybe_mergeable_pair : maybe_mergeable_luts) {
				log_assert(
						lut_edges_fw[maybe_mergeable_pair.first].contains(
								maybe_mergeable_pair.second));
				pool<HlsNetNode*> unique_inputs;
				for (auto fst_lut_pred : lut_edges_bw[maybe_mergeable_pair.first])
					if (lut_nodes.contains(fst_lut_pred))
						unique_inputs.insert(fst_lut_pred);
				for (auto snd_lut_pred : lut_edges_bw[maybe_mergeable_pair.second])
					if (lut_nodes.contains(snd_lut_pred))
						unique_inputs.insert(snd_lut_pred);
				unique_inputs.erase(maybe_mergeable_pair.first);
				if ((int) unique_inputs.size() <= order) {
					if (debug_relax)
						log("      Breaking may allow merging %s and %s.\n",
								log_signal(maybe_mergeable_pair.first),
								log_signal(maybe_mergeable_pair.second));
					r_im++;
				}
			}

			int lut_gate_depth;
			if (lut_nodes.contains(lut_gate))
				lut_gate_depth = lut_depths[lut_gate];
			else {
				lut_gate_depth = 0;
				for (auto lut_gate_pred : lut_edges_bw[lut_gate])
					lut_gate_depth = max(lut_gate_depth,
							lut_depths[lut_gate_pred] + 1);
			}
			if (lut_depths[lut] >= lut_gate_depth + 1)
				r_slk = 0;
			else {
				int depth_delta = lut_gate_depth + 1 - lut_depths[lut];
				if (depth_delta > lut_slacks[lut]) {
					if (debug_relax)
						log(
								"      Breaking would increase depth by %d, which is more than available slack.\n",
								depth_delta);
					continue;
				}

				if (debug_relax) {
					log("      Breaking increases depth of LUT by %d.\n",
							depth_delta);
					const pool<HlsNetNode*> &_lut_critical_outputs =
							lut_critical_outputs.at(lut);
					if (_lut_critical_outputs.size()) {
						log("      Breaking decreases slack of outputs");
						for (auto lut_critical_output : _lut_critical_outputs) {
							log(" %s", log_signal(lut_critical_output));
							log_assert(lut_slacks[lut_critical_output] > 0);
						}log(".\n");
					}
				}
				r_slk = lut_critical_outputs.at(lut).size() * depth_delta;
			}

			int p = 100 * (r_alpha * r_ex + r_beta * r_im + r_gamma)
					/ (r_slk + 1);
			if (debug_relax)
				log(
						"    Potential for breaking node %s: %d (Rex=%d, Rim=%d, Rslk=%d).\n",
						log_signal(lut_gate), p, r_ex, r_im, r_slk);
			potentials[lut][lut_gate] = p;
		}
	}
}

pair<pool<HlsNetNode*>, pool<HlsNetNode*>> FlowmapAreaOpt::cut_lut_at_gate(
		HlsNetNode *lut, HlsNetNode *lut_gate) {
	pool<HlsNetNode*> gate_inputs = lut_edges_bw[lut];
	pool<HlsNetNode*> other_inputs;
	pool<HlsNetNode*> worklist = { lut };
	while (!worklist.empty()) {
		HlsNetNode *node = worklist.pop();
		for (auto &node_pred : edges_bw[node]) {
			if (node_pred == lut_gate)
				continue;
			if (lut_gates[lut].contains(node_pred))
				worklist.insert(node_pred);
			else {
				gate_inputs.erase(node_pred);
				other_inputs.insert(node_pred);
			}
		}
	}
	return {gate_inputs, other_inputs};
}

}
