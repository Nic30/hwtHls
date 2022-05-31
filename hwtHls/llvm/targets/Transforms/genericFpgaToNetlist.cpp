#include "genericFpgaToNetlist.h"
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
#include "../genericFpgaInstrInfo.h"
#include "../genericFpgaTargetPassConfig.h"

#define DEBUG_TYPE "genericfpga-tonetlist"

using namespace llvm;
namespace hwtHls {

char GenericFpgaToNetlist::ID = 0;

void GenericFpgaToNetlist::getAnalysisUsage(llvm::AnalysisUsage &AU) const {
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
bool GenericFpgaToNetlist::runOnMachineFunction(llvm::MachineFunction &MF) {
	LLVM_DEBUG(
			dbgs() << "********** GenericFpgaToNetlist **********\n"
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
	//errs() << "Loops:" << "\n";
	for (auto loop : Loops) {
		MachineBasicBlock *H = loop->getHeader();
		//errs() << *H << "\n";
		for (auto HPred : H->predecessors()) {
			if (loop->contains(HPred)) {
				backedges.insert( { HPred, H });
			}
		}
	}
	auto liveness = hwtHls::getLiveVariablesForBlockEdge(MF);
	std::vector<Register> ioRegs(MF.getFunction().arg_size());
	for (auto & R: ioRegs) {
		R = 0;
	}
	std::vector<MachineInstr*> toRm;
	for (auto & MB: MF) {
		for (auto & MI: MB) {
			if (MI.getOpcode() == GenericFpga::GENFPGA_ARG_GET) {
				uint64_t arg = MI.getOperand(1).getImm();
				assert(ioRegs[arg] == 0);
				ioRegs.at(arg) = MI.getOperand(0).getReg();
				toRm.push_back(&MI);
			}
		}
	}
	for (auto * MI: toRm) {
		MI->eraseFromParent();
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
	auto &GenFpga_TPC = *dynamic_cast<llvm::GenericFpgaTargetPassConfig*>(&TPC);
	(*GenFpga_TPC.toNetlistConversionFn)(MF, backedges, liveness, ioRegs, registerTypes);
	return true;
}

INITIALIZE_PASS_BEGIN(GenericFpgaToNetlist, DEBUG_TYPE, "GenericFpgaToNetlist", false,
                false)
INITIALIZE_PASS_DEPENDENCY(MachineLoopInfo)
INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
//INITIALIZE_PASS_END expanded
  PassInfo *PI = new PassInfo(
  	  "Run python callback to translate MIR to HlsNetlist", DEBUG_TYPE, &GenericFpgaToNetlist::ID,
      PassInfo::NormalCtor_t(callDefaultCtor<GenericFpgaToNetlist>), false, false);
  Registry.registerPass(*PI, true);
  return PI;
}
static llvm::once_flag InitializeGenericFpgaToNetlistFlag;

void initializeGenericFpgaToNetlist(PassRegistry &Registry) {
    llvm::call_once(InitializeGenericFpgaToNetlistFlag,
    		hwtHls::initializeGenericFpgaToNetlistPassOnce, std::ref(Registry));
}

}
