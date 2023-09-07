#pragma once

#include <unordered_map>

#include "../reachabilityCpp/Graph.h"

namespace hwtHls::reachability {

class DagGraphWithDFSReachQuery: public DAGGraph {
protected:
	std::unordered_map<Vertex*, int> visited;
	int operationCounter;
	int _opCnt;

public:
	using DAGGraph::DAGGraph;

	bool isReachable(Vertex*, Vertex*);

	virtual ~DagGraphWithDFSReachQuery();

private:
	bool _isReachable(Vertex*, Vertex*);
};

}
