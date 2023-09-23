#include <hwtHls/llvm/targets/Transforms/completeLiveVRegs.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/InitializePasses.h>

#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

using namespace llvm;

#define DEBUG_TYPE "hwthls-completelivevregs"

namespace {

/* Check every possible CFG path and for uses and defines and resolve dead and killed MachineOperand flags
 * */
class CompleteLiveVRegs: public MachineFunctionPass {
	const TargetRegisterInfo *TRI;
	const TargetInstrInfo *TII;
	MachineRegisterInfo *MRI;

public:
	static char ID; // Pass identification, replacement for typeid

	CompleteLiveVRegs() :
			MachineFunctionPass(ID) {
		initializeCompleteLiveVRegsPass(*PassRegistry::getPassRegistry());
	}

	void getAnalysisUsage(AnalysisUsage &AU) const override {
		MachineFunctionPass::getAnalysisUsage(AU);
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

};

} // end anonymous namespace

char CompleteLiveVRegs::ID = 0;

INITIALIZE_PASS(CompleteLiveVRegs, DEBUG_TYPE,
		"Complete Virtual Register Liveness Pass", false, false)

bool CompleteLiveVRegs::runOnMachineFunction(MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	bool Changed = false;

	TRI = MF.getSubtarget().getRegisterInfo();
	TII = MF.getSubtarget().getInstrInfo();
	MRI = &MF.getRegInfo();

	auto livenessPredSuc = hwtHls::getLiveVariablesForBlockEdge(*MRI, MF);
	// reverse src->dst to dst->src
	std::map<MachineBasicBlock*, std::set<Register>> mbbLiveOuts;

	for (auto liv : livenessPredSuc) {
		auto *srcMbb = liv.first;
		for (auto &_liv : liv.second) {
			// auto * dstMbb =  _liv.first;
			auto cur = mbbLiveOuts.find(srcMbb);
			if (cur == mbbLiveOuts.end()) {
				mbbLiveOuts[srcMbb] = { };
				cur = mbbLiveOuts.find(srcMbb);
			}
			for (auto r : _liv.second)
				cur->second.insert(r);
		}
	}

	for (auto liv : mbbLiveOuts) {
		auto & currentlyLiveRegs = liv.second;
		for (MachineInstr &MI : reverse(*liv.first)) {
			if (MI.getOpcode() == HwtFpga::HWTFPGA_ARG_GET) {
				continue; // excluded from liveness analysis
			}
			// walk block from end and if reg is not used after mark it as dead if is def or killed if is use
			size_t MO_index = 0;
			SmallVector<Register, 8> usesToAdd;
			for (MachineOperand &MO : MI.operands()) {
				if (MO.isReg()) {
					if (currentlyLiveRegs.find(MO.getReg())
							== currentlyLiveRegs.end()) {
						if (MO.isDef()) {
							// is not used ever after -> dead
							MO.setIsDead();
						} else if (MO.isUse()) {
							bool isLastMOWithThisReg = true;
							for (auto _MO_index = MO_index + 1;
									_MO_index < MI.getNumOperands();
									++_MO_index) {
								auto _MO = MI.getOperand(_MO_index);
								if (_MO.isReg()) {
									assert(_MO.isUse());
									if (_MO.getReg() == MO.getReg()) {
										isLastMOWithThisReg = false;
										break;
									}
								}
							}
							if (isLastMOWithThisReg)
								MO.setIsKill(); // is last user -> kill
							usesToAdd.push_back(MO.getReg());
						}
					} else if (MO.isDef()) {
						currentlyLiveRegs.erase(MO.getReg());
					} else if (MO.isUse()) {
						usesToAdd.push_back(MO.getReg());
						currentlyLiveRegs.insert(MO.getReg());
 					}
				}
				++MO_index;
			}
			currentlyLiveRegs.insert(usesToAdd.begin(), usesToAdd.end());
		}
	}

	return Changed;
}

namespace hwtHls {
FunctionPass* createCompleteLiveVRegsPass() {
	return new CompleteLiveVRegs();
}
}
