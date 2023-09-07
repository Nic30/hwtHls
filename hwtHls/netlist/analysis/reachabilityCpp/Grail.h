// rewrite of https://github.com/zakimjz/dagger-index modified for graphs without SCCs

#pragma once
#include <vector>
#include <map>
#include <unordered_map>

#include "../reachabilityCpp/Graph.h"

namespace hwtHls::reachability {

class DagGraphWithGrailReachQuery: DAGGraph {
public:
	struct label {
		Vertex **pre;
		Vertex **post;
		label(int dim) {
			pre = new Vertex*[2 * dim];
			post = pre + dim;
		}
		label() :
				pre(nullptr), post(nullptr) {
		}
		label(label &cp, int dim) {
			pre = new Vertex*[2 * dim];
			post = pre + dim;
			for (int i = 0; i < 2 * dim; i++) {
				pre[i] = cp.pre[i];
			}
		}
		~label() {
			delete[] pre;
		}
	};

	class compare_pairs {
	public:
		bool operator()(const std::pair<int, int> x, const std::pair<int, int> y) const {
			if (x.first == y.first)
				return x.second - y.second;
			return (x.first - y.first) < 0;
		}
	};

	using LabelList = std::unordered_map<int, label>;
	using MyMap = std::unordered_map<int, int>;
	using PQueue = std::map<std::pair<int, int>, int, compare_pairs>;

protected:
	int size;
	int dim;
	std::unordered_map<int, label> labels;
	MyMap visited;

	int operationCounter;
	int inc;
	int _opCnt;

public:
	DagGraphWithGrailReachQuery(Graph &graph, int Dim, int increment);
	virtual ~DagGraphWithGrailReachQuery();
	void integrityCheck();
	virtual void edgeAdded(int, int);
	virtual void edgeDeleted(int, int);
	virtual void nodeAdded(int, std::vector<int>&, std::vector<int>&);
	virtual void nodeDeleted(int);
	virtual bool query(Vertex *, Vertex *);
	virtual bool contains(Vertex *, Vertex *);
	void dagEdgeAdded(int, int);
	void dagEdgeRemoved(int, int);
	void componentsMerged(int center, vector<int> &list);
	void componentSplit(int center, MySet &clist, int trg);

private:
	void randomLabeling(int);
	void visit(int node, int tra, int &post);
	void propagateUp(int, int, int);
	int findPaths(int, int, std::vector<int>&);
	bool rquery(Vertex *, Vertex *);
	void extractList(EdgeList::iterator first, EdgeList::iterator last,
			std::back_insert_iterator<std::vector<int> > result);
	void splitVisit(int s, MySet &clist, int stval, int endval, int d, int &counter, PQueue &pqueue);

	void propagateUpStart(int, int, int);
	void propagateUpEnd(int, int, int);
	void pQueueProcess(PQueue &pqueue, int d);
};

}
