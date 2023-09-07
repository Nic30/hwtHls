#include "../reachabilityCpp/Grail.h"

#include <algorithm>

using namespace std;

namespace hwtHls::reachability {

DagGraphWithGrailReachQuery::DagGraphWithGrailReachQuery(int Dim, int increment) :
		dim(Dim), dag(graph), inc(increment) {

	VertexSet::iterator it;
	for (auto &vid : vertices) {
		if (labels.find(vid.get()) == labels.end())
			labels.insert(LabelList::value_type(vid, label(dim)));
	}
	for (int i = 0; i < dim; i++) {
		_opCnt++;
		randomLabeling(i);
	}
}

DagGraphWithGrailReachQuery::~DagGraphWithGrailReachQuery() {
}

void DagGraphWithGrailReachQuery::integrityCheck() {
	LabelList::iterator lit;
	EdgeList::iterator eit;
	EdgeList _trick;
	for (lit = labels.begin(); lit != labels.end(); lit++) {
		for (int j = 0; j < dim; j++) {
			if (lit->second.pre[j] < 0 || lit->second.post[j] < lit->second.pre[j] + dag.csize[lit->first] * inc) {
				cout << " DAG NODE " << lit->first << " has invalid labels at " << j << " [" << lit->second.pre[j]
						<< "," << lit->second.post[j] << "]" << endl;
			}
			EdgeList &tel = dag.getOutEdges(lit->first, _trick);
			for (eit = tel.begin(); eit != tel.end(); eit++) {
				if (lit->second.pre[j] > labels[eit->first].pre[j]
						|| lit->second.post[j] < labels[eit->first].post[j]) {
					cout << " DAG NODE " << lit->first << " has invalid labels at " << j << " [" << lit->second.pre[j]
							<< "," << lit->second.post[j] << "] ---> " << eit->first << " ["
							<< labels[eit->first].pre[j] << "," << labels[eit->first].post[j] << "] " << endl;
				}
			}
		}
	}
}

bool DagGraphWithGrailReachQuery::query(Vertex *src, Vertex *trg) {
	if (src == trg)
		return 1;
	_opCnt++;
	return rquery(src, trg);
}

void DagGraphWithGrailReachQuery::nodeDeleted(Vertex *nid) {
	labels.erase(nid);
	dag.removeNode(nid);
}
void DagGraphWithGrailReachQuery::nodeAdded(int src, vector<int> &incoming, vector<int> &outgoing) {
	labels.insert(LabelList::value_type(src, label(dim)));
	dag.dagsize++;
	label &nl = labels[src];
	int next;
	// assign initial labels checking children
	if (outgoing.size() != 0) {
		next = dag.getScc(outgoing[0]);
		dag.addDagEdge(src, next, 1);
		label &ref = labels[next];
		for (int i = 0; i < dim; i++) {
			nl.pre[i] = ref.pre[i];
			nl.post[i] = ref.post[i];
		}

		for (int j = 1; j < outgoing.size(); j++) {
//			cout << "adding outgoing edge " << endl;
			next = dag.getScc(outgoing[j]);
			dag.addDagEdge(src, next, 1);
			label &ref = labels[next];
			for (int i = 0; i < dim; i++) {
				if (nl.pre[i] > ref.pre[i])
					nl.pre[i] = ref.pre[i];
				if (nl.post[i] < ref.post[i])
					nl.post[i] = ref.post[i];
			}
		}
		for (int i = 0; i < dim; i++) {
			nl.post[i] += inc;
		}
	} else if (incoming.size() != 0) {
		label &ref = labels[dag.getScc(incoming[0])];
		for (int i = 0; i < dim; i++) {
			if (ref.pre[i] == ref.post[i] - inc) {
				nl.pre[i] = ref.post[i] - inc;
				nl.post[i] = ref.post[i];
			} else {
				nl.post[i] = ref.post[i] - inc;
				nl.pre[i] = nl.post[i] - inc;
			}
//			cout << "setting somethint here " << nl.pre[i] << "-" << nl.post[i] << endl;
//			cout << "setting somethint here " << dag.getScc(incoming[0]) << " "<< ref.pre[i] << "-" << ref.post[i] << endl;
		}
	} else {
		for (int i = 0; i < dim; i++) {
			nl.post[i] = dag.orig.size() * inc;
			nl.pre[i] = nl.post[i] - inc;
			if (nl.post[i] < 0 || nl.pre[i] < 0) {
				std::runtime_error("error while adding node witout inputs/outputs");
			}
		}
	}
}

void DagGraphWithGrailReachQuery::componentsMerged(int center, vector<int> &list) {
	if (labels.find(center) == labels.end())
		labels.insert(LabelList::value_type(center, label(dim)));
	label &clabel = labels[center];
//	cout << " CM 1 list.size = " << list.size() << endl;
//	for(int i=0;i<list.size();i++)
//		cout << " " << list[i];
//	cout << " CM 1.1" << endl;
	label &tlabel = labels[list.back()];

	for (int i = 0; i < dim; i++) {
		clabel.pre[i] = tlabel.pre[i];
		clabel.post[i] = tlabel.post[i] - 1;
	}
//	cout << " CM 2" << endl;

	for (int i = 0; i < list.size(); i++) {
		if (list[i] != center)
			labels.erase(list[i]);
	}
//	cout << " CM 3" << endl;

	for (int i = 0; i < dim; i++) {
		propagateUpStart(center, i, clabel.pre[i]);
//		cout << "finished up start " << endl;
		propagateUpEnd(center, i, clabel.post[i] + 1);
//		cout << "finished up end " << endl;
	}
//	cout << " CM 4" << endl;

}

void DagGraphWithGrailReachQuery::componentSplit(int center, MySet &clist, int trg) {
	MySet::iterator mit;
//	dag.writeMap();
//	cout << "CS 1" << endl;
	for (mit = clist.begin(); mit != clist.end(); mit++) {
//		cout << *mit << endl;
		if (*mit == trg) {
			labels.insert(LabelList::value_type(*mit, label(labels[center], dim)));
			labels.erase(center);
			center = trg;
		} else if (*mit != center)
			labels.insert(LabelList::value_type(*mit, label(dim)));
	}
//	cout << "CS 2" << endl;
	label &clabel = labels[center];
//	cout << "CS 3" << endl;
	for (int i = 0; i < dim; i++) {
		_opCnt++;
//		cout << "CS 3.1" << endl;
		int counter = clabel.pre[i];
		PQueue pqueue;
//		cout << "CS 3.2" << endl;
		splitVisit(center, clist, clabel.pre[i], clabel.post[i], i, counter, pqueue);
//		cout << "CS 3.3" << endl;
		pQueueProcess(pqueue, i);
//		cout << "CS 3.4" << endl;
	}
//	cout << "CS 4" << endl;
}

void DagGraphWithGrailReachQuery::splitVisit(int s, MySet &clist, int stval, int endval, int d, int &counter,
		PQueue &pqueue) {
	int end = counter;
	EdgeList _trick;
	vector<int> shuffled;
	vector<int>::iterator sit;
//	cout << "SV 1 " << endl;
	EdgeList &temp = dag.getOutEdges(s, _trick);
//	cout << "SV 2 " << endl;
	extractList(temp.begin(), temp.end(), std::back_inserter(shuffled));
//	cout << "SV 3 " << endl;
	std::random_shuffle(shuffled.begin(), shuffled.end());
//	cout << "SV 4 " << endl;
	visited[s] = _opCnt;
//	cout << "SV 5 " << endl;
	for (sit = shuffled.begin(); sit != shuffled.end(); sit++) {
		if (clist.find(*sit) != clist.end() && visited[*sit] != _opCnt)
			splitVisit(*sit, clist, stval, endval, d, counter, pqueue);
		int x = labels[*sit].post[d];
		if (end < x)
			end = x;
	}
//	cout << "SV 6 " << endl;
	counter += dag.getNodeSize(s) * inc;
	end = max(end + inc, counter);
//	cout << "SV 7 " << s << endl;
	label &slabel = labels[s];
//	cout << "SV 7.1 " << endl;
	slabel.pre[d] = stval;
//	cout << "SV 7.2 " << endl;
	slabel.post[d] = end;
//	cout << "SV 8 " << endl;

	if (end > endval) {
		EdgeList &el = dag.getInEdges(s, _trick);
		EdgeList::iterator eit;
		for (eit = el.begin(); eit != el.end(); eit++) {
			label &plabel = labels[eit->first];
			if (clist.find(eit->first) == clist.end() && plabel.post[d] <= end) {
				pqueue.insert(make_pair(make_pair(plabel.post[d], eit->first), end + inc));
			}
		}
	}

}

void DagGraphWithGrailReachQuery::dagEdgeAdded(Vertex *parent, Vertex *child) {
//	cout << "adding dag edge" << endl;

	label &pl = labels[parent];
	label &cl = labels[child];
//	cout << " DEA 1" << endl;
	for (int i = 0; i < dim; i++) {
		if (pl.pre[i] > cl.pre[i]) {
			pl.pre[i] = cl.pre[i];
//			cout << " DEA 2.1.s." << i << endl;
			propagateUpStart(parent, i, pl.pre[i]);
//			cout << " DEA 2.1.e." << i << endl;
		}
		if (pl.post[i] < cl.post[i] + inc) {
//			cout << " DEA 2.2.s." << i << endl;
			propagateUpEnd(parent, i, cl.post[i] + inc);
//			cout << " DEA 2.2.e." << i << endl;
		}
	}
}

void DagGraphWithGrailReachQuery::dagEdgeRemoved(int parent, int child) {
//	cout << "removing dag edge" << endl;
	// do nothing
}
void DagGraphWithGrailReachQuery::propagateUpStart(int parent, int d, int val) {
	EdgeList temp;
	EdgeList &el = dag.getInEdges(parent, temp);
	for (EdgeList::iterator eit = el.begin(); eit != el.end(); eit++) {
		label &nextlabel = labels[eit->first];
		if (nextlabel.pre[d] > val) {
			nextlabel.pre[d] = val;
			propagateUpStart(eit->first, d, val);
		}
	}
}

void DagGraphWithGrailReachQuery::propagateUpEnd(int parent, int d, int val) {
	PQueue pqueue;
	pqueue.insert(make_pair(make_pair(0, parent), val));
//	cout << " PUE 1 " << endl;
	pQueueProcess(pqueue, d);
//	cout << " PUE 2 " << endl;
}

void DagGraphWithGrailReachQuery::pQueueProcess(PQueue &pqueue, int d) {
	PQueue::iterator eit;
	EdgeList::iterator pit;
//	cout << " PQP 1 " << pqueue.size() << " " << pqueue.begin()->first.second <<endl;
	while (!pqueue.empty()) {
//		cout << " PQP 1 " << pqueue.size() << " " << pqueue.begin()->first.second <<endl;
//		cout << " PQP 1.1" << endl;
		eit = pqueue.begin();
//		cout << " PQP 1.2" << endl;
		Vertex * parent = (eit->first).second;
		label &curl = labels[parent];
//		cout << " PQP 1.3" << endl;
		if (curl.post[d] < eit->second) {
//			cout << " PQP 1.3.1 setting the value of " << parent << " to "<<eit->second << endl;
//			writeIndex();
			curl.post[d] = eit->second;
//			cout << " PQP 1.3.1-2" << endl;
		} else {
//			cout << " PQP 1.3.2 "<< parent << "  is already larger than the queued value, skipping..." << endl;
			pqueue.erase(eit);
			continue;
		}
//		cout << " PQP 2 " << endl;
		EdgeList temp;
		EdgeList &el = dag.getInEdges(parent, temp);
		for (pit = el.begin(); pit != el.end(); pit++) {
			label &nextl = labels[pit->first];
			if (nextl.post[d] < eit->second + inc) {
//				cout << "processing "  << parent << ": inserting " << pit->first << " into the queue with value ((" << nextl.post[d] <<
//				               "," << pit->first << ")," << eit->second+inc << ")"<< endl;
				pqueue.insert(make_pair(make_pair(nextl.post[d], pit->first), eit->second + inc));
//				cout << "size of pqueue is " << pqueue.size() << endl;

			}
		}
//		cout << " PQP 3 " << endl;
		pqueue.erase(eit);
//		cout << " PQP 4 " << endl;
	}
}

bool DagGraphWithGrailReachQuery::rquery(Vertex *src, Vertex *trg) {
	visited[src] = _opCnt;
	if (src == trg)
		return 1;
	EdgeList &el = src->outEdges();
	EdgeList::iterator it;
	for (it = el.begin(); it != el.end(); it++) {
		Vertex *next = it->first;
		if (visited[next] != _opCnt && contains(next, trg)) {
			if (rquery(next, trg))
				return 1;
		}
	}
	return 0;
}

bool DagGraphWithGrailReachQuery::contains(Vertex *src, Vertex *trg) {
	label &sl = labels[src];
	label &tl = labels[trg];
	for (int i = 0; i < dim; i++) {
		if (sl.pre[i] > tl.pre[i] || sl.post[i] <= tl.pre[i])
			return 0;
	}
	return 1;
}

void DagGraphWithGrailReachQuery::randomLabeling(int tra) {
	int post = 0;
	vector<int>::iterator sit;
	vector<int> shuffled;
	std::copy(roots.begin(), roots.end(), std::back_inserter(shuffled));
	random_shuffle(shuffled.begin(), shuffled.end());
	for (sit = shuffled.begin(); sit != shuffled.end(); sit++) {
		if (visited[*sit] != _opCnt)
			visit(*sit, tra, post);
	}
}

void DagGraphWithGrailReachQuery::visit(Vertex *node, int tra, int &post) {
	visited[node] = _opCnt;
	vector<int>::iterator sit;
	vector<int> shuffled;
	EdgeList _trick;
	EdgeList &temp = dag.getOutEdges(node, _trick);
	extractList(temp.begin(), temp.end(), std::back_inserter(shuffled));
	std::random_shuffle(shuffled.begin(), shuffled.end());
	int min = post;
	for (sit = shuffled.begin(); sit != shuffled.end(); sit++) {
		if (visited[*sit] != _opCnt)
			visit(*sit, tra, post);
		if (labels[*sit].pre[tra] < min)
			min = labels[*sit].pre[tra];
	}
	labels[node].pre[tra] = min;
	post += inc * dag.getNodeSize(node);
	labels[node].post[tra] = post;
}

void DagGraphWithGrailReachQuery::extractList(EdgeList::iterator first, EdgeList::iterator last,
		std::back_insert_iterator<vector<int> > result) {
	while (first != last) {
		*result = first->first;
		first++;
		result++;
	}
}

}
