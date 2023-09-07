#include "../reachabilityCpp/Vertex.h"

#include <sstream>

namespace hwtHls::reachability {

using namespace std;


Vertex::Vertex() {
}

Vertex::~Vertex() {
}

void Vertex::eraseOutEdge(Vertex* x){
	outList.erase(x);
}
EdgeList& Vertex::outEdges(){
	return outList;
}
EdgeList& Vertex::inEdges(){
	return inList;
}
int Vertex::outDegree(){
	return outList.size();
}
int Vertex::inDegree(){
	return inList.size();
}
int Vertex::degree(){
	return inList.size()+outList.size();
}
int Vertex::hasEdge(Vertex* endNode){
	return outList.find(endNode) != outList.end();
}
void Vertex::addInEdge(Vertex* sid){
	inList[sid]++;
}
void Vertex::addOutEdge(Vertex* tid){
	outList[tid]++;
}

}
