#include "liveVariableForEdge.h"
#include <tuple>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>

// * Boissinot, B., Hack, S., Grund, D., de Dinechin, B. D., & Rastello, F. (2008). Fast Liveness Checking for SSA-Form Programs. CGO.
// * Domaine, & Brandner, Florian & Boissinot, Benoit & Darte, Alain & Dinechin, Benoît & Rastello, Fabrice. (2011).
//   Computing Liveness Sets for SSA-Form Programs.
// * https://github.com/lijiansong/clang-llvm-tutorial/blob/master/live-variable-analysis/Liveness.md
// * Attention this variant works also for non SSA MIR IR
using namespace llvm;
namespace hwtHls {

template<typename T>
class UniqList: public std::vector<T> {
private:
	std::set<T> _set;
public:
	void push_back(T item) {
		if (_set.find(item) == _set.end()) {
			_set.insert(item);
			std::vector<T>::push_back(item);
		}
	}
	bool contains(T item) {
		return _set.find(item) != _set.end();
	}
};

std::pair<UniqList<Register>, UniqList<std::pair<Register, MachineBasicBlock*>> > collect_direct_provieds_and_requires(
		MachineBasicBlock &block) {
	UniqList<Register> provides;
	UniqList<std::pair<Register, MachineBasicBlock*>> req;

	for (auto &i : block.instrs()) {
		unsigned opCnt = i.getNumOperands();
		// uses must be seen first, defs after
		for (unsigned _i = opCnt; _i > 0 ; --_i) {
			auto & v = i.getOperand(_i - 1);
			if (!v.isReg()) {
				continue;
			}
			if (v.isDef()) {
				provides.push_back(v.getReg());
			} else if (!provides.contains(v.getReg())) {
				req.push_back( { v.getReg(), nullptr });
			}
		}
	}

	return {provides, req};
}

void recursively_add_edge_requirement_var(
		std::map<MachineBasicBlock*, UniqList<Register>> &provides,
		MachineBasicBlock *src, MachineBasicBlock *dst, Register v,
		EdgeLivenessDict &live) {
	auto &_live = live[src][dst];

	if (_live.find(v) != _live.end()) {
		return;
	}

	_live.insert(v);
	if (!provides[src].contains(v)) {
		for (auto *pred : src->predecessors()) {
			recursively_add_edge_requirement_var(provides, pred, src, v, live);
		}
	}
}

EdgeLivenessDict getLiveVariablesForBlockEdge(MachineFunction &MF) {
	EdgeLivenessDict live;
	std::map<MachineBasicBlock*, UniqList<Register>> provides;
	std::map<MachineBasicBlock*,
			UniqList<std::pair<Register, MachineBasicBlock*>>> reqs;
	// initialization
	for (MachineBasicBlock &block : MF) {
		std::tie(provides[&block], reqs[&block]) =
				collect_direct_provieds_and_requires(block);
		auto &sucs = live[&block] = std::map<MachineBasicBlock*, std::set<Register>>();
		for (auto *suc : block.successors()) {
			sucs[suc] = std::set<Register>();
		}
	}
	// transitive enclosure of requires relation
	for (MachineBasicBlock &block : MF) {
		for (auto _req : reqs[&block]) {
			Register req;
			MachineBasicBlock *req_if_predecessor_is;
			std::tie(req, req_if_predecessor_is) = _req;
			if (req_if_predecessor_is == nullptr) {
				// requires from all predecessors
				for (auto *pred : block.predecessors()) {
					recursively_add_edge_requirement_var(provides, pred, &block,
							req, live);
				}
			} else {
				recursively_add_edge_requirement_var(provides,
						req_if_predecessor_is, &block, req, live);
			}
		}
	}
	return live;
}

}
