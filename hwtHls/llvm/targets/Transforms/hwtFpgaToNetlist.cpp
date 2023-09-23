#include "hwtFpgaToNetlist.h"

#include <llvm/CodeGen/MachineBranchProbabilityInfo.h>
//#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineLoopInfo.h>
#include <llvm/CodeGen/MachineOptimizationRemarkEmitter.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/MachineTraceMetrics.h>
#include <llvm/CodeGen/LiveVariables.h>
#include "../hwtFpgaInstrInfo.h"
#include "../hwtFpgaTargetPassConfig.h"

#define DEBUG_TYPE "hwtfpga-tonetlist"

using namespace llvm;
namespace hwtHls {

char HwtFpgaToNetlist::ID = 0;

void HwtFpgaToNetlist::getAnalysisUsage(llvm::AnalysisUsage &AU) const {
	//AU.addRequired<MachineBranchProbabilityInfo>();
	//AU.addRequired<MachineDominatorTree>();
	//AU.addPreserved<MachineDominatorTree>();
	//AU.setPreservesCFG();
	AU.addRequired<TargetPassConfig>();
	AU.addPreserved<TargetPassConfig>();
	AU.addRequired<MachineLoopInfo>();
	AU.addPreserved<MachineLoopInfo>();
	//AU.addRequired<MachineTraceMetrics>();
	//AU.addPreserved<MachineTraceMetrics>();
	// LiveVariables supports only SSA
	//AU.addRequired<LiveVariables>();
	//AU.addPreserved<LiveVariables>();

	MachineFunctionPass::getAnalysisUsage(AU);
}

void collectBackedges(
		std::set<HwtFpgaToNetlist::MachineBasicBlockEdge> &backedges,
		const MachineLoop &loop) {
	MachineBasicBlock *H = loop.getHeader();
	for (auto HPred : H->predecessors()) {
		if (loop.contains(HPred)) {
			backedges.insert( { HPred, H });
		}
	}
	for (const MachineLoop *chLoop : loop) {
		collectBackedges(backedges, *chLoop);
	}
}

bool HwtFpgaToNetlist::runOnMachineFunction(llvm::MachineFunction &MF) {
	LLVM_DEBUG(
			dbgs() << "********** HwtFpgaToNetlist **********\n"
					<< "********** Function: " << MF.getName() << '\n');
	if (skipFunction(MF.getFunction()))
		return false;
	//const TargetSubtargetInfo &STI = MF.getSubtarget();
	//const TargetInstrInfo *TII;
	//const TargetRegisterInfo *TRI;
	//MCSchedModel SchedModel;
	//MachineDominatorTree *DomTree;
	//MachineTraceMetrics *Traces;
	//TII = STI.getInstrInfo();
	//TRI = STI.getRegisterInfo();
	//SchedModel = STI.getSchedModel();
	MachineRegisterInfo *MRI = &MF.getRegInfo();
	//DomTree = &getAnalysis<MachineDominatorTree>();
	MachineLoopInfo &Loops = getAnalysis<MachineLoopInfo>();
	//Traces = &getAnalysis<MachineTraceMetrics>();
	std::set<MachineBasicBlockEdge> backedges;
	for (auto loop : Loops) {
		collectBackedges(backedges, *loop);
	}
	auto livenessPredSuc = hwtHls::getLiveVariablesForBlockEdge(*MRI, MF);
	std::vector<Register> ioRegs(MF.getFunction().arg_size());
	for (auto &R : ioRegs) {
		R = 0;
	}
	for (auto &MB : MF) {
		for (auto &MI : MB) {
			if (MI.getOpcode() == HwtFpga::HWTFPGA_ARG_GET) {
				uint64_t arg = MI.getOperand(1).getImm();
				assert(ioRegs[arg] == 0);
				ioRegs.at(arg) = MI.getOperand(0).getReg();
			}
		}
	}
	for (auto &R : ioRegs) {
		if (R == 0) {
			throw std::runtime_error(
					"The machine function body is missing use of IO argument");
		}
	}
	std::map<llvm::Register, unsigned> registerTypes;
	auto regNum = MRI->getNumVirtRegs();
	for (unsigned r = 0; r < regNum; r++) {
		Register R = Register::index2VirtReg(r);
		LLT T = MRI->getType(R);
		if (T.isValid()) {
			registerTypes[R] = T.getSizeInBits();
		}
	}
	auto &TPC = getAnalysis<TargetPassConfig>();
	auto &HwtFpga_TPC = *dynamic_cast<llvm::HwtFpgaTargetPassConfig*>(&TPC);
	(*HwtFpga_TPC.toNetlistConversionFn)(MF, backedges, livenessPredSuc, ioRegs,
			registerTypes, Loops);
	return true;
}

INITIALIZE_PASS_BEGIN(HwtFpgaToNetlist, DEBUG_TYPE, "HwtFpgaToNetlist", false,
		false)
	INITIALIZE_PASS_DEPENDENCY(MachineLoopInfo)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
//INITIALIZE_PASS_END expanded
	PassInfo *PI = new PassInfo(
			"Run python callback to translate MIR to HlsNetlist", DEBUG_TYPE,
			&HwtFpgaToNetlist::ID,
			PassInfo::NormalCtor_t(callDefaultCtor<HwtFpgaToNetlist>), false,
			false);
	Registry.registerPass(*PI, true);
	return PI;
}
static llvm::once_flag InitializeHwtFpgaToNetlistFlag;

void initializeHwtFpgaToNetlist(PassRegistry &Registry) {
	llvm::call_once(InitializeHwtFpgaToNetlistFlag,
			hwtHls::initializeHwtFpgaToNetlistPassOnce, std::ref(Registry));
}

}
