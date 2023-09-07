#pragma once

#include <unordered_map>
#include <iostream>

namespace hwtHls::reachability {

class Vertex;

using EdgeList = std::unordered_map<Vertex*, int>;

class Vertex {
public:
	EdgeList inList;
	EdgeList outList;
	EdgeList& outEdges();
	EdgeList& inEdges();
	int outDegree();
	int inDegree();
	int degree();
	int hasEdge(Vertex *end);
	void addOutEdge(Vertex *tid);
	void addInEdge(Vertex *sid);
	void eraseOutEdge(Vertex *x);

	Vertex(int);
	Vertex();
	virtual ~Vertex();
};

}
