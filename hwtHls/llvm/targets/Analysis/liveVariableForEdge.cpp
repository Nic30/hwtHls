#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>

#include <tuple>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <hwtHls/llvm/targets/hwtFpgaMCTargetDesc.h>

// * Boissinot, B., Hack, S., Grund, D., de Dinechin, B. D., & Rastello, F. (2008). Fast Liveness Checking for SSA-Form Programs. CGO.
// * Domaine, & Brandner, Florian & Boissinot, Benoit & Darte, Alain & Dinechin, Benoît & Rastello, Fabrice. (2011).
//   Computing Liveness Sets for SSA-Form Programs.
// * https://github.com/lijiansong/clang-llvm-tutorial/blob/master/live-variable-analysis/Liveness.md
// * Attention this variant works also for non SSA MIR IR
using namespace llvm;
namespace hwtHls {

bool isInstructionWhichIsKeeptOutOfLiveness(llvm::MachineRegisterInfo &MRI,
		const llvm::MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_ARG_GET:
		return true;  // constant which represents the IO port
	case HwtFpga::HWTFPGA_GLOBAL_VALUE:
		return true;  // constant which represents the local memory
	case HwtFpga::IMPLICIT_DEF:
		auto def = MRI.getOneDef(MI.getOperand(0).getReg());
		if (def && def->getParent() == &MI) {
			return true; // constant undef
		}
		break;
	}
	return false;
}

void collectDirectLiveinsAndDefines(llvm::MachineRegisterInfo &MRI,
		MachineBasicBlock &block,
		std::function<
				bool(llvm::MachineRegisterInfo &MRI,
						const llvm::MachineInstr &MI)> ignoreInstrPredicate,
		SetVector<std::pair<Register, MachineBasicBlock*>> &liveins,
		SetVector<Register> &defines) {
	assert(liveins.empty());
	assert(defines.empty());

	for (auto &i : block.instrs()) {
		if (ignoreInstrPredicate(MRI, i))
			continue;
		unsigned opCnt = i.getNumOperands();
		if (i.isPHI()) {
		    for (unsigned Idx = 1; Idx < i.getNumOperands(); Idx += 2) {
		      const MachineOperand &Src = i.getOperand(Idx);
		      Register SrcReg = Src.getReg();
		      const MachineOperand &_SrcMBB = i.getOperand(Idx+1);
		      MachineBasicBlock * SrcMBB = _SrcMBB.getMBB();
		      liveins.insert( { SrcReg, SrcMBB });
		    }
			defines.insert(i.getOperand(0).getReg());
		} else {
			// uses must be seen first, defs after
			for (unsigned _i = opCnt; _i > 0; --_i) {
				auto &v = i.getOperand(_i - 1);
				if (!v.isReg()) {
					continue;
				}
				if (v.isDef() || v.isUndef()) {
					defines.insert(v.getReg());
				} else if (!defines.contains(v.getReg())) {
					auto r = v.getReg();
					if (auto *defMO = MRI.getOneDef(r)) {
						if (ignoreInstrPredicate(MRI, *defMO->getParent())) {
							continue;
						}
					}
					liveins.insert( { r, nullptr });
				}
			}
		}
	}
}

void recursivelyAddEdgeRequirementVar(
		std::map<MachineBasicBlock*, SetVector<Register>> &provides,
		MachineBasicBlock *src, MachineBasicBlock *dst, Register v,
		EdgeLivenessDict &live) {
	auto &_live = live[src][dst];

	if (_live.find(v) != _live.end()) {
		return;
	}

	_live.insert(v);
	if (!provides[src].contains(v)) {
		for (auto *pred : src->predecessors()) {
			recursivelyAddEdgeRequirementVar(provides, pred, src, v, live);
		}
	}
}

EdgeLivenessDict getLiveVariablesForBlockEdge(MachineRegisterInfo &MRI,
		MachineFunction &MF) {
	EdgeLivenessDict live;
	std::map<MachineBasicBlock*, SetVector<Register>> defines;
	std::map<MachineBasicBlock*,
			SetVector<std::pair<Register, MachineBasicBlock*>>> liveins;
	// initialization
	for (MachineBasicBlock &block : MF) {
		liveins[&block] = SetVector<std::pair<Register, MachineBasicBlock*>>();
		defines[&block] = SetVector<Register>();
		collectDirectLiveinsAndDefines(MRI, block,
				isInstructionWhichIsKeeptOutOfLiveness, liveins[&block],
				defines[&block]);
		auto &sucs = live[&block] = std::map<MachineBasicBlock*,
				std::set<Register>>();
		for (auto *suc : block.successors()) {
			sucs[suc] = std::set<Register>();
		}
	}
	// transitive enclosure of requires relation
	for (MachineBasicBlock &block : MF) {
		for (auto _req : liveins[&block]) {
			Register req;
			MachineBasicBlock *req_if_predecessor_is;
			std::tie(req, req_if_predecessor_is) = _req;
			if (req_if_predecessor_is == nullptr) {
				// requires from all predecessors
				for (auto *pred : block.predecessors()) {
					recursivelyAddEdgeRequirementVar(defines, pred, &block,
							req, live);
				}
			} else {
				recursivelyAddEdgeRequirementVar(defines,
						req_if_predecessor_is, &block, req, live);
			}
		}
	}
	return live;
}

}
