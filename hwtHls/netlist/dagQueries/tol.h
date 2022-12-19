#pragma once

#include "tolHeap.h"
#include "tolMap.h"
#include "tolTolLevelHash.h"
#include "tolVector.h"

namespace TOL {

// Andy Diwen Zhu, Wenqing Lin, Sibo Wang, and Xiaokui Xiao. 2014. Reachability queries on large dynamic graphs: a total order approach.
// In Proceedings of the 2014 ACM SIGMOD International Conference on Management of Data (SIGMOD '14).
// Association for Computing Machinery, New York, NY, USA, 1323–1334. https://doi.org/10.1145/2588555.2612181
// based on https://sourceforge.net/projects/totalorderlabeling/ (complete rewrite)
// which is based on https://github.com/A-Pisani/Reachability-Queries-in-Directed-Graphs
// other similar things
//   * https://github.com/spaghetti-source/algorithm/blob/master/graph/dynamic_reachability_dag.cc
//   * https://github.com/zakimjz/dagger-index/tree/master/DGRAIL
// successors:
//   * https://github.com/dabianzhixing/DBL
//   * https://github.com/wael34218/Neo4Reach
//
// note:
//   * does not edges with same src and dst (multigraph)
class ReachabilityIndexTOLButterfly {
public:
	using Node_t = unsigned;
	enum Dir_t {
		OUT = 0, IN = 1,
	};
	static constexpr std::array<Dir_t, 2> dirs = { Dir_t::OUT, Dir_t::IN };
	static constexpr size_t DIR_CNT = 2;

private:
	struct Triple {
		Node_t x, y;
		Dir_t dir;
		Triple() :
				x(0), y(0), dir(Dir_t::OUT) {
		}
		Triple(int xx, int yy, Dir_t ww) {
			x = xx;
			y = yy;
			dir = ww;
		}

		inline bool operator<(const Triple &e) const {
			if (x < e.x)
				return true;
			else if (x > e.x)
				return false;
			else if (y < e.y)
				return true;
			else if (y > e.y)
				return false;
			else
				return dir < e.dir;
		}
		inline bool operator==(const Triple &e) const {
			return (x == e.x && y == e.y);
		}
	};

	static constexpr double COST_LIMIT = 1e20;

	// temporary collections are defined there in order to avoid reallocations
	std::vector<Node_t> tmpN2x[DIR_CNT]; // temporary vector
	std::vector<Node_t> tmpQ; // temporary queue
	std::vector<Node_t> tmpRnodes; // temporary queue for DeleteNode
	TolHeap<Node_t> tmpOpq;
	std::vector<Node_t> tmpList[DIR_CNT]; // temporary queues used in addNode, upgradeNode, addEdge
	std::vector<bool> tmpNodeModified;
	TolMap<int> tmpMark, tmpCleanmark; // -1 is used to mark unreachable, INT_MAX is a handle

	/*
	 * Reverse direction value
	 * */
	static inline Dir_t dirReverse(Dir_t dir) {
		return Dir_t(1 - unsigned(dir));
	}
	template<typename T>
	static inline T costAddSaturate(T &dst, const T &toAdd) {
		dst += toAdd;
		if (dst > COST_LIMIT)
			dst = COST_LIMIT;
		return dst;
	}
	template<typename T>
	static inline T roundToPowerOf2(T x) {
		T power = 1;
		while (power < x)
			power *= 2;
		return power;
	}
	size_t nodeCount;
	// level is the total order of the node, l(v) ∈ [1, |V|]
	std::vector<unsigned> node2level;
	std::vector<int> level2node;
	std::array<std::vector<int>, DIR_CNT> order;
	std::vector<Triple> candi; // candidate set

	// Definition of TOL Indices:
	//  * L_in(v) is a set of nodes u, u→v,
	//  * l(u) < l(v)
	//  * No simple path from u to v contains a vertex w with l(w) < l(u)
	// = TOL label sets are build for each node for each direction, L_in is a set of predecessor nodes
	// with total order lower than this node, if there is a path to predecessor
	// from this node which contains node with lower total order the predecessor
	// is not in the set
	std::array<std::vector<TolVector<Node_t>>, DIR_CNT> labels; // L_out(v), L_in(v)
	std::array<std::vector<TolVector<Node_t>>, DIR_CNT> backlabels; // inverted index of labels: I_in(u) = {w | u ∈ L_in(w)}
	std::array<std::vector<TolVector<Node_t>>, DIR_CNT> links; // neighbor sets for each direction for each node

	TolLevelHash levelhash;

	//bool bicheck(int p, Dir_t dir, int t);
	void labelUpdate();
	bool consystencyCheck(Node_t src, Node_t dst, Dir_t dir, Node_t z);
	bool consystencyCheck2(Node_t src, Node_t dst, Dir_t dir, TolLevelHash &lh);
	int upgradeNode(Node_t n);
	void refineCandidates();
	void applyCandidateSet(Node_t n, Node_t y);
	double getPqItemFromCost(Node_t i,
			std::array<std::vector<double>, DIR_CNT> &cost);

	/*
	 * Add label if does not exits and use tmpCleanmark to reduce number of compares during the search
	 * */
	inline bool addLabelCleanmark(Node_t src, Node_t dst, Dir_t dir,
			int index) {
		size_t setSize = labels[dir][src].size();
		unsigned o = tmpCleanmark.occur.size();

		// check if the label exits
		if (o > 0 && setSize > 0) {
			unsigned x = setSize / (o * 8);
			if (x > 30 || setSize < (1u << x)) {
				// if set is large use binary search
				for (unsigned j = 0; j < o; j++) {
					unsigned p = tmpCleanmark.occur[j];
					unsigned left = 0;
					unsigned _right = setSize;
					for (; left < _right;) {
						// binary search for p in labels[dir][src]
						unsigned m = (left + _right) / 2;
						x = labels[dir][src][m];

						if (x == p) {
							// label exists we do not need to insert
							return false;
						} else if (x < p)
							left = m + 1;
						else
							_right = m;
					}
				}
			} else {
				// use linear search
				for (auto l : labels[dir][src])
					if (tmpCleanmark.exist(l)) {
						// label exists we do not need to insert
						return false;
					}
			}
		}

		labels[dir][src].push_back(index);
		return true;
	}

	inline bool addLabel1(Node_t src, Node_t dst, Dir_t dir) {
		assert(src < nodeCount);
		assert(dst < nodeCount);
		if (_isReachable(src, dst, dir)) {
			return false;
		}
		labels[dir][src].sorted_insert(dst);
		backlabels[dir][dst].sorted_insert(src);

		return true;
	}

public:
	ReachabilityIndexTOLButterfly() :
			nodeCount(0) {
	}

	// disable copy constructor to prevent accidental copy of this very heavy object
	ReachabilityIndexTOLButterfly(const ReachabilityIndexTOLButterfly&) = delete;
	ReachabilityIndexTOLButterfly& operator=(
			const ReachabilityIndexTOLButterfly&) = delete;
	void resize(size_t maxNodeCount);

	/*
	 * :attention: loadGraph does not compute index automatically
	 * */
	void loadGraph(size_t nodeCnt,
			const std::vector<std::pair<Node_t, Node_t>> &edges);
	// upper estimation = R1, lower estimation = P1 from original code
	void computeIndex(bool upperEstimation);
	void computeBacklink();
	// BFS compute order of the nodes and index heuristic costs in both directions
	static void computeOrderAndCost(
			std::array<std::vector<TolVector<Node_t>>, DIR_CNT> &links,
			bool upperEstimation,
			std::array<std::vector<double>, DIR_CNT> &cost,
			std::array<std::vector<int>, DIR_CNT> &order,
			std::vector<Node_t> &tmpQ);

	void addNode(Node_t n, const std::vector<Node_t> neighbors_in,
			const std::vector<Node_t> neighbors_out, bool append);
	void addEdge(Node_t src, Node_t dst);
	void deleteNode(Node_t n);

	//bool checkCircle(Node_t src, Node_t dst, Dir_t dir);
	/*
	 * Implements query alg. for 2-hop labeling method
	 * */
	bool isReachable(Node_t src, Node_t dst);
	bool _isReachable(Node_t src, Node_t dst, Dir_t dir);

	//void optimize();
	//void reduce();

};

}
