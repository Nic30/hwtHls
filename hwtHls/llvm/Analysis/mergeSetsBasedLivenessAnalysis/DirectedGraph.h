#pragma once
#include <unordered_map>
#include <vector>
#include <queue>
#include <unordered_set>
#include <algorithm>

namespace hwtHls {


/*
 * This class of DirectedGraph contains bidirectional dictionary
 * for fast iteration of incoming and outgoing edges.
 * As the side effect the data of edge is duplicated so simple data or shared pointer should be used.
 * */
template<typename Node, typename EdgeData>
class DirectedGraph {
public:
	struct Edge {
		Node other;
		EdgeData data;
	};

private:
	std::unordered_map<Node, std::vector<Edge>> adj;
	std::unordered_map<Node, std::vector<Edge>> reverseAdj;
	std::unordered_map<Node, unsigned> nodeOrder;
	const std::vector<Edge> _emptyEdges;
public:
	bool addNode(const Node &n) {
		if (adj.count(n))
			return false;
		adj[n] = { };
		reverseAdj[n] = { };
		nodeOrder[n] = nodeOrder.size();
		return true;
	}

	bool removeNode(const Node &n) {
		if (!adj.count(n))
			return false;
		adj.erase(n);
		reverseAdj.erase(n);
		nodeOrder.erase(n);
		for (auto& [u, edges] : adj) {
			edges.erase(
					std::remove_if(edges.begin(), edges.end(),
							[&](const Edge &e) {
								return e.other == n;
							}), edges.end());
		}
		for (auto& [u, edges] : reverseAdj) {
			edges.erase(
					std::remove_if(edges.begin(), edges.end(),
							[&](const Edge &e) {
								return e.other == n;
							}), edges.end());
		}
		return true;
	}

	void addEdge(const Node &u, const Node &v, const EdgeData &ed) {
		assert(adj.count(u));
		assert(adj.count(v));
		adj[u].push_back( { v, ed });
		reverseAdj[v].push_back( { u, ed });
	}

	bool removeEdge(const Node &u, const Node &v) {
		auto &outs = adj[u];
		auto oldOut = outs.size();
		outs.erase(std::remove_if(outs.begin(), outs.end(), [&](const Edge &e) {
			return e.other == v;
		}), outs.end());
		auto &ins = reverseAdj[v];
		auto oldIn = ins.size();
		ins.erase(std::remove_if(ins.begin(), ins.end(), [&](const Edge &e) {
			return e.other == u;
		}), ins.end());
		return outs.size() != oldOut || ins.size() != oldIn;
	}

	const std::vector<Edge>& incomingEdgesOf(const Node &n) const {
		auto it = reverseAdj.find(n);
		if (it != reverseAdj.end())
			return it->second;
		return _emptyEdges;
	}

	const std::vector<Edge>& outgoingEdgesOf(const Node &n) const {
		auto it = adj.find(n);
		if (it != adj.end())
			return it->second;
		return _emptyEdges;
	}

	std::vector<Node> breadthFirst(const Node &start) const {
		std::vector<Node> result;
		auto it = adj.find(start);
		if (it == adj.end())
			return result;

		std::queue<Node> q;
		std::unordered_set<Node> visited;
		q.push(start);
		visited.insert(start);

		while (!q.empty()) {
			Node u = q.front();
			q.pop();
			result.push_back(u);
			for (const auto &e : adj.at(u)) {
				if (visited.insert(e.other).second) {
					q.push(e.other);
				}
			}
		}

		// Sort nodes based on their insertion order
		std::sort(result.begin(), result.end(),
				[&](const Node &a, const Node &b) {
					return nodeOrder.at(a) < nodeOrder.at(b);
				});

		return result;
	}

	const auto& allNodes() const {
		return adj;
	}
};

}
