#include "../reachabilityCpp/Graph.h"

#include <istream>
#include <stdlib.h>
#include <string>
#include <sstream>
#include <assert.h>

namespace hwtHls::reachability {

DAGGraph::DAGGraph() :
		vsize(0), edgeCount(0) {
}

DAGGraph::~DAGGraph() {
}

size_t DAGGraph::size() {
	return vsize;
}

void DAGGraph::insertEdge(Vertex *sid, Vertex *tid) {
	assert(vertices.count(static_cast<std::unique_ptr<Vertex>>(sid)) == 1 && "node must be present");
	assert(vertices.count(static_cast<std::unique_ptr<Vertex>>(tid)) == 1 && "node must be present");
	sid->addOutEdge(tid);
	tid->addInEdge(sid);
	edgeCount++;
	NotifyEdgeInsertion(sid, tid);
}

void DAGGraph::deleteEdge(Vertex *sid, Vertex *tid) {
	assert(vertices.count(static_cast<std::unique_ptr<Vertex>>(sid)) == 1 && "node must be present");
	assert(vertices.count(static_cast<std::unique_ptr<Vertex>>(tid)) == 1 && "node must be present");
	sid->outEdges().erase(tid);
	tid->inEdges().erase(sid);
	edgeCount--;
	NotifyEdgeDeletion(sid, tid);
}

Vertex* DAGGraph::insertNode(const Vertices &incoming, const Vertices &outgoing) {
	auto nid = std::make_unique<Vertex>();
	vsize++;
	auto *_nid = nid.get();
	vertices.insert(std::move(nid));

	EdgeList &el = _nid->outEdges();
	for (auto o : outgoing) {
		el[o] = 1;
		o->addInEdge(_nid);
	}
	NotifyNodeInsertion(_nid, incoming, outgoing);
	edgeCount += outgoing.size();

	for (auto i : incoming) {
		insertEdge(i, _nid);
	}
	return _nid;
}

// First delete outedges then remove
void DAGGraph::deleteNode(Vertex *nid) {
	vsize--;
	EdgeList &el = nid->outEdges();
	while (el.size()) {
		deleteEdge(nid, el.begin()->first);
	}
	NotifyNodeDeletion(nid);
	EdgeList &el2 = nid->inEdges();
	edgeCount -= el2.size();
	EdgeList::iterator eit = el2.begin();
	while (eit != el2.end()) {
		Vertex *next = eit->first;
		next->outEdges().erase(nid);
		eit++;
	}
	vertices.erase(static_cast<std::unique_ptr<Vertex>>(nid));
}

size_t DAGGraph::edgeSize() {
	return edgeCount;
}

}
