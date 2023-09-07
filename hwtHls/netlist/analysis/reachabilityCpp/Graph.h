#pragma once

#include <unordered_map>
#include <iostream>
#include <set>
#include <vector>
#include <memory>

#include "../reachabilityCpp/Vertex.h"

namespace hwtHls::reachability {

/**
 * DAG graph
 * * owns the Vertex objects, vertexes are deleted after remove from graph
 * */
class DAGGraph {
public:
	using VertexSet = std::set<std::unique_ptr<Vertex>>;
	using Vertices = std::vector<Vertex*>;

public:
	DAGGraph();

	VertexSet vertices;
	size_t vsize;
	size_t edgeCount;

	void insertEdge(Vertex *sid, Vertex *tid);
	void deleteEdge(Vertex *sid, Vertex *tid);
	Vertex* insertNode(const Vertices &incoming, const Vertices &outgoing);
	void deleteNode(Vertex *sid);

	virtual void NotifyEdgeDeletion(Vertex *src, Vertex *trg) {
	}
	virtual void NotifyEdgeInsertion(Vertex *src, Vertex *trg) {
	}
	virtual void NotifyNodeInsertion(Vertex *nid, const Vertices &incoming, const Vertices &outgoing) {
	}
	virtual void NotifyNodeDeletion(Vertex *src) {
	}

	size_t size();
	size_t edgeSize();
	virtual ~DAGGraph();
};

}
