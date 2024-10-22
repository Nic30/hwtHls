#pragma once

#include <base/abc/abc.h>
#include <map>
#include <string>
#include <unordered_set>

namespace hwtHls {

// Convert external non-oscilatory combinational loops to an acyclic form
Abc_Ntk_t* Abc_NtkExpandExternalCombLoops(Abc_Ntk_t *pNtk, Abc_Aig_t *pMan,
		const  std::map<Abc_Obj_t*, std::unordered_set<Abc_Obj_t*>>& impliedValues,
		const std::map<Abc_Obj_t*, Abc_Obj_t*> &inToOutConnections,
		const std::unordered_set<Abc_Obj_t*> &trueOutputs);

}
