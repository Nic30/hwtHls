#include <cstdio>
#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include "tol.h"

#include "tolHeap.h"

using namespace std;

namespace TOL {

constexpr int TOPNUM = 1;

//bool ReachabilityIndexTOLButterfly::checkCircle(Node_t src, Node_t dst,
//		Dir_t dir) {
//	Dir_t dRev = dirReverse(dir);
//	auto &_labels = labels[dRev][dst];
//	for (size_t i = 0; i < _labels.size(); ++i) {
//		if (_labels[i] == src) {
//			unsigned cnt = 0;
//			for (unsigned j = 0, k = 0;
//					j < backlabels[dRev][src].size()
//							&& k < backlabels[dRev][dst].size();) {
//				int x = backlabels[dRev][src][j];
//				int y = backlabels[dRev][dst][k];
//				if (x == y) {
//					cnt++;
//					++k;
//					++j;
//				} else if (x < y)
//					j++;
//				else
//					k++;
//			}
//			if (cnt == backlabels[dRev][dst].size()) {
//				return true;
//			} else
//				return false;
//		}
//	}
//	return false;
//}

//bool ReachabilityIndexTOLButterfly::bicheck(int p, Dir_t dir, int t) {
//	unsigned l = 0;
//	auto &_labels = labels[dir][t];
//	unsigned r = _labels.size();
//	for (; l < r;) {
//		int m = (l + r) / 2;
//		if (int(_labels[m]) == p)
//			return true;
//		if (int(_labels[m]) < p)
//			l = m + 1;
//		else
//			r = m;
//	}
//	return false;
//}

//void ReachabilityIndexTOLButterfly::optimize() {
//	levelhash.initialize(level, 30);
//	for (unsigned i = 0; i < nodeCount - TOPNUM; ++i) {
//		upgradeNode(l2n[nodeCount - 1 - i]);
//	}
//}

void ReachabilityIndexTOLButterfly::loadGraph(size_t nodeCnt,
		const std::vector<std::pair<Node_t, Node_t>> &edges) {
	assert(nodeCount == 0);
	resize(nodeCnt);

	for (auto &edge : edges) {
		Node_t y, x;
		std::tie(x, y) = edge;
		links[OUT][x].push_back(y);
		links[IN][y].push_back(x);
	}
	levelhash.initialize(node2level, 10);

}

void ReachabilityIndexTOLButterfly::resize(size_t maxNodeCount) {
	assert(maxNodeCount > nodeCount);
	tmpMark.reserve(maxNodeCount);
	tmpMark.resize(maxNodeCount);
	tmpCleanmark.reserve(maxNodeCount);
	tmpCleanmark.resize(maxNodeCount);
	tmpNodeModified.reserve(maxNodeCount);
	tmpNodeModified.resize(maxNodeCount);
	tmpQ.reserve(maxNodeCount);
	tmpQ.reserve(maxNodeCount);
	tmpOpq.initialize(nodeCount);

	for (Dir_t dir : dirs) {
		labels[dir].reserve(maxNodeCount);
		labels[dir].resize(maxNodeCount);

		links[dir].reserve(maxNodeCount);
		links[dir].resize(maxNodeCount);

		backlabels[dir].reserve(maxNodeCount);
		backlabels[dir].resize(maxNodeCount);

		order[dir].reserve(maxNodeCount);
		order[dir].resize(maxNodeCount);
		for (Node_t i = nodeCount; i < maxNodeCount; ++i) {
			order[dir][i] = 0;
		}
	}

	node2level.reserve(maxNodeCount);
	node2level.resize(maxNodeCount);
	level2node.reserve(maxNodeCount);
	level2node.resize(maxNodeCount);
	for (Node_t i = nodeCount; i < maxNodeCount; ++i) {
		node2level[nodeCount] = maxNodeCount;
		level2node[i] = -1;
	}

	nodeCount = maxNodeCount;
}

double ReachabilityIndexTOLButterfly::getPqItemFromCost(Node_t n,
		std::array<std::vector<double>, DIR_CNT> &cost) {
	if (cost[OUT][n] > COST_LIMIT || cost[IN][n] > COST_LIMIT) {
		return -COST_LIMIT * COST_LIMIT * (links[OUT][n].size() + 1)
				* (links[IN][n].size() + 1);
	} else {
		return -(cost[OUT][n] - 1) * (cost[IN][n] - 1)
				/ (cost[OUT][n] + cost[IN][n]);
	}
}

void ReachabilityIndexTOLButterfly::computeIndex(bool upperEstimation) {
	// initializations
	std::array<std::vector<double>, DIR_CNT> cost; // dir X node
	for (Dir_t dir : dirs) {
		cost[dir].reserve(nodeCount);
		cost[dir].resize(nodeCount);
	}
	assert(tmpCleanmark.size() == 0);
	assert(tmpMark.size() == 0);
	tmpCleanmark.initialize(nodeCount);
	computeOrderAndCost(links, upperEstimation, cost, order, tmpQ);
	// compute hierarchies
	TolHeap<double> pq;
	pq.initialize(nodeCount);

	for (Node_t id = 0; id < nodeCount; ++id) {
		pq.insert(id, getPqItemFromCost(id, cost));
		node2level[id] = nodeCount;
	}

	vector<double> tcost(nodeCount);
	for (Node_t id = 0; id < nodeCount; ++id) {
		// get top node with lazy update
		Node_t p;
		for (;;) {
			p = pq.head();
			pq.insert(p, getPqItemFromCost(p, cost));
			if (pq.head() == p) {
				p = pq.pop();
				break;
			}
		}

		//find children of p, mark them, and create back labels
		tmpQ.push_back(p);
		tmpMark.insert(p, 2);
		tcost[p] = 0;

		tmpCleanmark.clear();
		for (auto l : labels[OUT][p]) {
			tmpCleanmark.insert(l, 1);
		}

		for (Node_t c : tmpQ) {
			if (addLabelCleanmark(c, p, OUT, id)) {
				for (Node_t t : links[OUT][c]) {
					if (node2level[t] == nodeCount) {
						if (tmpMark.notexist(t)) {
							tmpMark.insert(t, 1);
							tmpQ.push_back(t);
							tcost[t] = 0;
						}
					}
				}
			}
		}
		tmpQ.clear();
		tmpCleanmark.clear();

		//find ancestors of p
		for (auto l : labels[IN][p]) {
			tmpCleanmark.insert(l, 1);
		}

		tmpQ.push_back(p);
		for (unsigned i = 0; i < tmpQ.size(); ++i) {
			Node_t c = tmpQ[i];

			if (addLabelCleanmark(c, p, IN, id)) {
				for (Node_t t : links[IN][c]) {
					if (node2level[t] == nodeCount) {
						if (tmpMark.notexist(t)) {
							tmpMark.insert(t, 2);
							tmpQ.push_back(t);
							tcost[t] = 0;
						} else {
							if (tmpMark.get(t) == 1) {
								throw std::runtime_error("DAG Property Error");
							}
						}
					}
				}
			}
		}
		tmpQ.clear();

		for (auto c : tmpMark.occur) {
			if (tmpMark.get(c) != 2) {
				continue;
			}
			for (Node_t t : links[OUT][c]) {
				if (node2level[t] == nodeCount
						&& (t == p || tmpMark.get(t) == 1)) {
					if (upperEstimation) {
						costAddSaturate(tcost[c], cost[IN][t]);
						costAddSaturate(tcost[t], cost[OUT][c]);
					} else {
						costAddSaturate(tcost[c],
								cost[IN][t] / links[IN][t].size());
						costAddSaturate(tcost[t],
								cost[OUT][c] / links[OUT][c].size());

					}
				}
			}
		}

		for (Node_t c : tmpMark.occur) {
			Node_t d = tmpMark.get(c) - 1;
			if (cost[d][c] < COST_LIMIT)
				cost[d][c] -= tcost[c];

			for (Node_t t : links[d][c]) {
				if (node2level[t] == nodeCount) {
					if (upperEstimation) {
						costAddSaturate(tcost[t], tcost[c]);
					} else {
						costAddSaturate(tcost[t],
								tcost[c] / links[d][c].size());
					}
				}
			}
		}

		node2level[p] = id;
		level2node[id] = p;
		tmpMark.clear();
	}

	//	reduce();
}

void ReachabilityIndexTOLButterfly::labelUpdate() {
	//label update
	for (Node_t p : tmpMark.occur) {
		if (tmpMark.get(p) >= 0) {
			Node_t c = tmpMark.get(p);

			if (tmpMark.get(c) >= 0) {
				throw std::runtime_error(
						"Error in marking for non crutial nodes\n");
			}
			candi.push_back(
					Triple(levelhash.N2L[c], p, Dir_t(tmpMark.get(c) + 2)));
		}
	}

	std::sort(candi.begin(), candi.end());
}

void ReachabilityIndexTOLButterfly::refineCandidates() {
	//clear candis while generating left and right wings
	std::sort(candi.begin(), candi.end());

	size_t j = 0;
	for (size_t i = 0; i < candi.size(); ++i) {
		Node_t p = candi[i].y;

		if (tmpMark.get(p) == int(p)) {
			if (i != j) {
				candi[j] = candi[i];
			}
			j++;

			Dir_t d = candi[i].dir;
			tmpMark.insert(p, 0);

			for (Node_t c : backlabels[dirReverse(d)][p]) {
				if (c != p
						&& (tmpMark.notexist(c) || tmpMark.get(c) == int(c))) {
					tmpMark.insert(c, p);
					tmpMark.inc(p);
				}
			}
		}
	}

	candi.resize(j);

}
void ReachabilityIndexTOLButterfly::applyCandidateSet(Node_t n, Node_t y) {
	for (auto &cand : candi) {
		Node_t p = cand.y;
		Dir_t d = cand.dir;
		Dir_t dRev = dirReverse(d);
		if (tmpMark.get(p) < 0) {
			if (levelhash.N2L[p] < int(y)) {
				addLabel1(n, p, d);
			} else {
				addLabel1(p, n, dRev);
				for (auto l : backlabels[d][n]) {
					if (l != p)
						tmpCleanmark.insert(l, 1);
				}
			}
			tmpList[d].push_back(p);
		} else if (cand.x >= y) {
			addLabel1(p, n, dRev);
			for (auto l : backlabels[d][n]) {
				if (l != p)
					tmpCleanmark.insert(l, 1);
			}
		}

		for (Node_t c : tmpList[dRev]) {
			if (addLabel1(p, c, dRev) == 1) {
				for (auto l : backlabels[d][c]) {
					if (l != c && l != p)
						tmpCleanmark.insert(l, 1);
				}
			}
		}

		if (tmpCleanmark.occur.size() > 0) {
			size_t k = 0;
			auto &_labels = labels[dRev][p];
			for (size_t j = 0; j < _labels.size(); ++j) {
				Node_t n1 = _labels[j];
				if (tmpCleanmark.notexist(n1)) {
					if (k != j) {
						_labels[k] = n1;
					}
					k++;
				} else {
					if (!backlabels[dRev][n1].remove(p)) {
						throw std::runtime_error("Backlabel deleting Error");
					}
				}
			}
			_labels.resize(k);

			tmpCleanmark.clear();
		}
	}

	tmpList[OUT].clear();
	tmpList[IN].clear();

	for (Dir_t dir : dirs) {
		addLabel1(n, n, dir);
	}

}

/*
 * @param nn probably neighbors count
 */
void ReachabilityIndexTOLButterfly::addNode(Node_t n,
		const std::vector<Node_t> neighbors_in,
		const std::vector<Node_t> neighbors_out, bool append) {
	if (n >= nodeCount) {
		resize(roundToPowerOf2<size_t>(n));
	}
	//compute level
	//compute potential candis
	const std::vector<Node_t> *neighbors[DIR_CNT];
	neighbors[OUT] = &neighbors_out;
	neighbors[IN] = &neighbors_in;
	assert(candi.size() == 0);
	assert(tmpMark.size() == 0);
	assert(tmpList[OUT].size() == 0);
	assert(tmpList[IN].size() == 0);

	for (Dir_t dir : dirs) {
		for (Node_t p : *neighbors[dir]) {
			for (Node_t c : labels[dir][p]) {
				if (tmpMark.notexist(c)) {
					if (levelhash.nottop(TOPNUM, c)) {
						candi.push_back(Triple(levelhash.N2L[c], c, dir));
						tmpMark.insert(c, c);
					} else {
						addLabel1(n, c, dir);
						tmpMark.insert(c, -10);
						tmpList[dir].push_back(c);
					}
				}
			}
		}
	}

	//compute level
	refineCandidates();

	//scan candis from lowest level to highest level
	int sum = 0, k = 0, y = levelhash.Last;

	assert(tmpN2x[OUT].empty());
	assert(tmpN2x[IN].empty());

	assert(candi.size() > 0);
	for (auto cand = candi.rbegin(); cand != candi.rend(); ++cand) {
		Node_t c = cand->y;
		Node_t l = cand->x;
		Dir_t d = cand->dir;
		if (!append) {
			Dir_t dRev = dirReverse(d);
			for (Node_t t : backlabels[dRev][c]) {
				if (tmpMark.get(t) == int(c) && t != c
						&& !consystencyCheck2(t, n, dRev, levelhash)) {
					sum++;
				}
			}
			for (auto t : tmpN2x[dRev]) {
				if (!consystencyCheck(t, c, d, n)) {
					sum--;
				}
			}

			if (sum < k) {
				k = sum;
				y = l;
			}

			for (auto t : backlabels[dRev][c]) {
				if (t != c && tmpMark.get(t) == int(c)) {
					tmpN2x[d].push_back(t);
				}
			}
			tmpN2x[d].push_back(c);
		}
		tmpMark.insert(c, d - 2);
	}

	labelUpdate();
	applyCandidateSet(n, y);
	//level update
	levelhash.insert(n, y);
	candi.clear();
	tmpMark.clear();
	tmpN2x[OUT].clear();
	tmpN2x[IN].clear();
}

bool ReachabilityIndexTOLButterfly::consystencyCheck(Node_t src, Node_t dst,
		Dir_t dir, Node_t z) {
	auto const &labels0 = labels[dir][src];
	auto const &labels1 = labels[dirReverse(dir)][dst];
	for (size_t i = 0, j = 0; i < labels0.size() && j < labels1.size();) {
		int x = labels0[i];
		int y = labels1[j];

		if (x == y && x != int(dst) && x != int(z))
			return true;
		else if (x < y)
			++i;
		else
			++j;
	}

	return false;
}

bool ReachabilityIndexTOLButterfly::consystencyCheck2(Node_t src, Node_t dst,
		Dir_t dir, TolLevelHash &lh) {
	auto const &labels0 = labels[dir][src];
	auto const &labels1 = labels[dirReverse(dir)][dst];
	for (unsigned i = 0, j = 0; i < labels0.size() && j < labels1.size();) {
		int x = labels0[i];
		int y = labels1[j];

		if (x == y && !lh.nottop(TOPNUM, x))
			return true;
		else if (x < y)
			++i;
		else
			++j;
	}

	return false;
}

//int ReachabilityIndexTOLButterfly::upgradeNode(Node_t n) {
//	//compute potential candis
//	assert(candi.size() == 0);
//	assert(mark.size() == 0);
//	for (Dir_t dir : dirs) {
//		for (auto p : links[dir][n]) {
//			for (auto c : labels[dir][p]) {
//				if (mark.notexist(c) && levelhash.nottop(TOPNUM, c)) {
//					mark.insert(c, c);
//					candi.push_back(Triple(levelhash.N2L[c], c, dir));
//				}
//			}
//		}
//	}
//
//	refineCandidates();
//
//	//scan candis from lowest level to highest level
//	int sum = 0, k = 0, y = levelhash.Last;
//	int tmp = 0;
//	bool flag = true;
//
//	assert(tmpN2x[OUT].empty());
//	assert(tmpN2x[IN].empty());
//	assert(candi.size() > 0);
//	for (auto cand = candi.rbegin(); cand != candi.rend(); ++cand) {
//		Node_t c = cand->y;
//		Node_t l = cand->x;
//		Dir_t d = cand->dir;
//		Dir_t dRev = dirReverse(d);
//
//		if (flag && int(l) < levelhash.N2L[n]) {
//			flag = false;
//			tmp = sum;
//		}
//
//		for (Node_t t : backlabels[dRev][c]) {
//			if (mark.get(t) == int(c) && t != c
//					&& !consystencyCheck2(t, n, dRev, levelhash)) {
//				sum++;
//			}
//		}
//		for (auto t : tmpN2x[dRev]) {
//			if (!consystencyCheck(t, c, d, n)) {
//				sum--;
//			}
//		}
//
//		if (sum < k) {
//			k = sum;
//			y = l;
//		}
//
//		for (auto t : backlabels[dRev][c]) {
//			if (t != c && mark.get(t) == int(c)) {
//				tmpN2x[d].push_back(t);
//			}
//		}
//		tmpN2x[d].push_back(c);
//
//		mark.insert(c, d - 2);
//	}
//	tmpN2x[OUT].clear();
//	tmpN2x[IN].clear();
//
//	if (flag)
//		tmp = sum;
//
//	if (tmp == k) {
//		candi.clear();
//		mark.clear();
//		return 0;
//	}
//
//	//label update
//	for (Dir_t dir : dirs) {
//		int j = 0;
//		for (auto c : labels[dir][n]) {
//			if (levelhash.nottop(TOPNUM, c)) {
//				if (c != n) {
//					if (!backlabels[dir][c].remove(n)) {
//						throw std::runtime_error(
//								"Backlabel deleting Error");
//					}
//				}
//			} else {
//				labels[dir][n][j] = c;
//				j++;
//			}
//		}
//		labels[dir][n].resize(j);
//
//		for (auto &backlabel : backlabels[dir][n]) {
//			if (backlabel != n) {
//				if (!labels[dir][backlabel].remove(n)) {
//					throw std::runtime_error("Label deleting Error");
//				}
//			}
//		}
//		backlabels[dir][n].clear();
//	}
//
//	labelUpdate();
//	applyCandidateSet(n, y);
//
//	//level update
//	levelhash.swap(n, y);
//
//	candi.clear();
//	mark.clear();
//	return tmp - k;
//}
//
void ReachabilityIndexTOLButterfly::computeBacklink() {
	for (Dir_t dir : dirs) {
		for (Node_t i = 0; i < nodeCount; ++i) {
			auto &_labels = labels[dir][i];
			for (size_t j = 0; j < _labels.size(); ++j) {
				_labels[j] = level2node[_labels[j]];
				backlabels[dir][_labels[j]].push_back(i);
			}
			if (_labels.size() > 0)
				_labels.sort();
		}
	}
}

void ReachabilityIndexTOLButterfly::deleteNode(Node_t n) {
	//update label
	for (Dir_t dir : dirs) {
		assert(tmpOpq.empty());
		Dir_t revDir = dirReverse(dir);
		assert(
				n < order[revDir].size()
						&& "Trying to remove node which was not added");
		tmpOpq.insert(n, order[revDir][n]);
		assert(tmpMark.size() == 0);
		tmpMark.insert(n, -1);

		for (; !tmpOpq.empty();) {
			Node_t p = tmpOpq.pop();
			tmpNodeModified[p] = false;

			bool flag = false;
			if (p != n) {
				flag = true;
				for (Node_t n : links[dir][p]) {
					if (tmpNodeModified[n]) {
						flag = false;
						break;
					}
				}
			}

			if (!flag) {
				assert(tmpRnodes.size() == 0);
				if (p != n) {
					//mark reachable nodes
					for (Node_t t : links[dir][p]) {
						if (t != n && t != p) {
							for (Node_t c : labels[dir][t]) {
								if (tmpMark.get(c) != int(p)) {
									tmpMark.insert(c, p);
									tmpRnodes.push_back(c);
								}
							}
						}
					}
				}

				//remove unreachable nodes from labels[dir][p]
				size_t j = 0;
				for (Node_t t : labels[dir][p]) {
					if ((t != p || t == n) && tmpMark.get(t) != int(p)) {
						backlabels[dir][t].remove(p);
						tmpNodeModified[p] = true;
					} else {
						tmpMark.insert(t, -1);
						labels[dir][p][j] = t;
						j++;
					}
				}
				labels[dir][p].resize(j);
				//add newly reachable nodes to labels[dir][p]
				for (Node_t t : tmpRnodes) {
					if (tmpMark.get(t) == int(p)
							&& levelhash.N2L[t] < levelhash.N2L[p]) {
						if (addLabel1(p, t, dir)) {
							tmpNodeModified[p] = true;
						}
					}
				}
				tmpRnodes.clear(); // temporary buffer private only to this "if"
			}

			//extend p
			if (levelhash.nottop(TOPNUM, p)) {
				for (Node_t c : links[revDir][p]) {
					if (tmpMark.notexist(c)) {
						tmpOpq.insert(c, order[revDir][c]);
						tmpMark.insert(c, -1);
					}
				}
			}
		}
		tmpMark.clear();
		tmpOpq.clear();
	}

	//links update
	for (Dir_t dir : dirs) {
		Dir_t revDir = dirReverse(dir);
		for (Node_t c : links[dir][n]) {
			links[revDir][c].remove_unsorted(n);
		}
		links[dir][n].clear();
	}

	//level update
	levelhash.remove(n);
	order[OUT] = INT_MAX;
	order[IN] = INT_MAX;
}

bool ReachabilityIndexTOLButterfly::isReachable(Node_t src, Node_t dst) {
	return _isReachable(src, dst, OUT);
}

bool ReachabilityIndexTOLButterfly::_isReachable(Node_t src, Node_t dst,
		Dir_t dir) {
	// W(s, t) = L_out(s) ∪ {s} ∩ L_in (t) ∪ {t}
	// W is witness set, if empty path it is not reachable else is
	assert(src < nodeCount);
	assert(dst < nodeCount);

	// find a any common item
	const auto &L_out_s = labels[dir][src];
	const auto &L_in_t = labels[dirReverse(dir)][dst];
	for (size_t i = 0, j = 0; i < L_out_s.size() && j < L_in_t.size();) {
		int x = L_out_s[i];
		int y = L_in_t[j];
		if (x == y) {
			return true;
		} else if (x < y) {
			i++;
		} else {
			j++;
		}
	}
	return false;
}

void ReachabilityIndexTOLButterfly::computeOrderAndCost(
		std::array<std::vector<TolVector<Node_t>>, DIR_CNT> &links,
		bool upperEstimation, std::array<std::vector<double>, DIR_CNT> &cost,
		std::array<std::vector<int>, DIR_CNT> &order,
		std::vector<Node_t> &tmpQ) {
	size_t nodeCount = links.size();
	std::vector<size_t> edgesRemaining(nodeCount + 1);
	// BFS compute topological order and cost
	for (Dir_t dir : dirs) {
		auto &_cost = cost[dir];
		auto &_order = order[dir];

		// initialization
		for (Node_t i = 0; i < nodeCount; ++i) {
			edgesRemaining[i] = links[dirReverse(dir)][i].size();
			if (edgesRemaining[i] == 0)
				tmpQ.push_back(i);

			_cost[i] = 1;
			_order[i] = 0;
		}

		// BFS
		for (Node_t n0 : tmpQ) {
			for (Node_t n1 : links[dir][n0]) {
				if (upperEstimation) {
					_cost[n1] += _cost[n0];
					if (_cost[n1] > COST_LIMIT) {
						_cost[n1] = COST_LIMIT * COST_LIMIT;
					}
				} else {
					costAddSaturate(_cost[n1],
							_cost[n0] / links[dir][n0].size());
				}
				_order[n1] = max(_order[n1], _order[n0] + 1);

				edgesRemaining[n1]--;
				if (edgesRemaining[n1] == 0)  // if all links have been seen
					tmpQ.push_back(n1);
			}
		}

		tmpQ.clear();
	}
}

void ReachabilityIndexTOLButterfly::addEdge(Node_t src, Node_t dst) {
	if (isReachable(src, dst))
		return;

	assert(tmpList[IN].size() == 0);
	assert(tmpList[OUT].size() == 0);
	Node_t V[2] = { src, dst };
	for (Dir_t dir : dirs) {
		Dir_t revDir = dirReverse(dir);
		auto &_labels = labels[revDir][V[dir]];
		auto &_backLabels = backlabels[revDir][V[revDir]];

		for (size_t i = 0; i < _labels.size(); ++i) {
			Node_t p = _labels[i];
			tmpList[revDir].push_back(p);
			for (auto bl : _backLabels) {
				addLabel1(bl, p, revDir);
			}
		}
	}

	for (Node_t src : tmpList[IN]) {
		for (Node_t dst : tmpList[OUT]) {
			if (node2level[src] < node2level[dst]) {
				for (Node_t tt : backlabels[IN][dst]) {
					addLabel1(tt, src, OUT);
				}
			} else {
				for (Node_t ss : backlabels[OUT][src]) {
					addLabel1(ss, dst, IN);
				}
			}
		}
	}
	tmpList[IN].clear();
	tmpList[OUT].clear();
}

//void ReachabilityIndexTOLButterfly::reduce() {
//	for (Dir_t dir : dirs) {
//		Dir_t revDir = dirReverse(dir);
//		for (Node_t i = 0; i < nodeCount; ++i) {
//			size_t x = 0;
//			for (Node_t p : labels[dir][i]) {
//				Node_t q = l2n[p];
//				bool flag = true;
//				if (q != i) {
//					for (auto l1 : labels[revDir][q]) {
//						if (tmpMark.get(l1) == int(i)) {
//							flag = false;
//							break;
//						}
//					}
//				}
//
//				if (flag) {
//					labels[dir][i][x] = p;
//					x++;
//				}
//
//				tmpMark.insert(p, i);
//			}
//			labels[dir][i].resize(x);
//		}
//	}
//}

}
