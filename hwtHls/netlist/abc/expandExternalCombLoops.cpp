#include <hwtHls/netlist/abc/expandExternalCombLoops.h>
#include <vector>
#include <unordered_map>
#include <set>
#include <stdexcept>

namespace hwtHls {

void * __attribute__ ((unused)) ___v0 = (void*) &Vec_MemHashProfile; // to suppress warning that Vec_MemHashProfile is unused


template<typename T>
class SetVector: private std::vector<T> {
	std::set<T> _set;
public:
	using std::vector<T>::vector;
	using std::vector<T>::begin;
	using std::vector<T>::end;
	using std::vector<T>::back;

	bool contains(T v) {
		return _set.find(v) != _set.end();
	}
	void push_back(T v) {
		if (!contains(v)) {
			_set.insert(v);
			std::vector<T>::push_back(v);
		}
	}
	void pop_back() {
		T& val = std::vector<T>::back();
		_set.erase(val);
		std::vector<T>::pop_back();
	}
};

Abc_Obj_t* _expandFanInCombLoops(Abc_Ntk_t *pNtk, Abc_Aig_t *pMan, Abc_Obj_t *v,
		const std::map<Abc_Obj_t*, Abc_Obj_t*> &inToOutConnections,
		SetVector<Abc_Obj_t*> &currentlyExpanding) {
	bool wasNegated = Abc_ObjIsComplement(v);
	v = Abc_ObjRegular(v);
	Abc_Obj_t *res = v;
	if (currentlyExpanding.contains(v))
		res = Abc_AigConst1(pNtk);
	else if (Abc_ObjIsPi(v)) {
		auto replacementPo = inToOutConnections.find(v);
		if (replacementPo != inToOutConnections.end()) {
			currentlyExpanding.push_back(v);
			res = _expandFanInCombLoops(pNtk, pMan,
					Abc_ObjFanin0(replacementPo->second), inToOutConnections,
					currentlyExpanding);
			res = Abc_ObjNotCond(res, Abc_ObjFaninC0(replacementPo->second));
			assert(currentlyExpanding.back() == v);
			currentlyExpanding.pop_back();
		}

	} else {
		switch (Abc_ObjFaninNum(v)) {
		case 0:
			break;
		case 2: {
			auto _v0 = Abc_ObjChild0(v);
			auto v0 = _expandFanInCombLoops(pNtk, pMan, _v0, inToOutConnections,
					currentlyExpanding);
			auto _v1 = Abc_ObjChild1(v);
			auto v1 = _expandFanInCombLoops(pNtk, pMan, _v1, inToOutConnections,
					currentlyExpanding);
			if (v0 != _v0 || v1 != _v1) {
				res = Abc_AigAnd(pMan, v0, v1);
			}
			break;
		}
		default:
			throw std::runtime_error("Node of unknown type in AIG");
		}

	}
	return Abc_ObjNotCond(res, wasNegated);
}

Abc_Ntk_t* Abc_NtkExpandExternalCombLoops(Abc_Ntk_t *pNtk, Abc_Aig_t *pMan,
		const std::map<Abc_Obj_t*, Abc_Obj_t*> &inToOutConnections,
		const std::unordered_set<Abc_Obj_t*> &trueOutputs) {
	for (auto o: trueOutputs) {
		if (!Abc_ObjIsPo(o)) {
			throw std::runtime_error("object in trueOutputs is not primary output");
		}
		if (Abc_ObjNtk(o) != pNtk) {
			throw std::runtime_error("object in trueOutputs is not from this network");
		}
	}

	// for each output create a new variant of expression where all terms which are in inToOutConnections are expanded
	std::unordered_map<Abc_Obj_t*, Abc_Obj_t*> outToIn;
	for (auto kv : inToOutConnections) {
		if (!Abc_ObjIsPi(kv.first)) {
			throw std::runtime_error("key object in inToOutConnections is not primary input");
		}
		if (!Abc_ObjIsPo(kv.second)) {
			throw std::runtime_error("value object in inToOutConnections is not primary output");
		}
		if (Abc_ObjNtk(kv.first) != pNtk) {
			throw std::runtime_error("key object in inToOutConnections is not from this network");
		}
		if (Abc_ObjNtk(kv.second) != pNtk) {
			throw std::runtime_error("value object in inToOutConnections is not from this network");
		}
		if (outToIn.contains(kv.second)) {
			throw std::runtime_error(
					"inToOutConnections input dictionary has duplicit values");
		}
		outToIn.insert({kv.second, kv.first});
	}
	int poIndex = 0;
	Abc_Obj_t *pPo = nullptr;
	std::vector<std::pair<Abc_Obj_t*, Abc_Obj_t*>> toReplace;
	toReplace.reserve(Abc_NtkPoNum(pNtk));

	// run expansion alg.
	Abc_NtkForEachPo( pNtk, pPo, poIndex )
	{
		auto associatedIn = inToOutConnections;
		SetVector<Abc_Obj_t*> currentlyExpanding;
		if (!trueOutputs.contains(pPo))
			continue; // this is only tmp variable
		// run expansion on this output
		currentlyExpanding.push_back(pPo);
		auto in0 = Abc_ObjChild0(pPo);
		auto in0Replacement = _expandFanInCombLoops(pNtk, pMan, in0,
				inToOutConnections, currentlyExpanding);
		// add into toReplace if value changed
		if (in0 != in0Replacement) {
			toReplace.push_back({pPo, in0Replacement});
		}
	}
	// apply resolved replacement
	for (const auto& [pPo, in0Replacement]: toReplace) {
		Abc_ObjPatchFanin(pPo, Abc_ObjFanin0(pPo), in0Replacement);
	}
	// cleanup unused outputs
	Abc_NtkForEachPo( pNtk, pPo, poIndex )
	{
		auto _trueOutput = trueOutputs.find(pPo);
		if (_trueOutput == trueOutputs.end())
			Abc_ObjPatchFanin(pPo, Abc_ObjFanin0(pPo), Abc_AigConst1(pNtk));
	}

	return pNtk;
}

}
