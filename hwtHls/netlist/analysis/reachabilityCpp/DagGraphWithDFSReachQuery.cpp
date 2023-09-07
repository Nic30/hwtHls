#include "../reachabilityCpp/DagGraphWithDFSReachQuery.h"

namespace hwtHls::reachability {

DagGraphWithDFSReachQuery::~DagGraphWithDFSReachQuery() {
}

bool DagGraphWithDFSReachQuery::isReachable(Vertex *src, Vertex *trg) {
	_opCnt++;
	return _isReachable(src, trg);
}

bool DagGraphWithDFSReachQuery::_isReachable(Vertex *src, Vertex *trg) {
	visited[src] = _opCnt;
	if (src == trg)
		return true;

	EdgeList &el = src->outEdges();
	EdgeList::iterator it;
	for (it = el.begin(); it != el.end(); it++) {
		if (visited[it->first] != _opCnt) {
			if (_isReachable(it->first, trg))
				return 1;
		}
	}
	return false;
}

}
