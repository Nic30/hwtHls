#include <hwtHls/llvm/targets/Transforms/concatBlockLiveins.h>

#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineLoopInfo.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/LiveVariables.h>
#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>
#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>

#define DEBUG_TYPE "hwtfpga-concatblockliveins"

using namespace llvm;
namespace hwtHls {

char ConcatBlockLiveins::ID = 0;

void ConcatBlockLiveins::getAnalysisUsage(llvm::AnalysisUsage &AU) const {
	AU.addRequired<MachineLoopInfo>();
	AU.addPreserved<MachineLoopInfo>();
	MachineFunctionPass::getAnalysisUsage(AU);
}

bool ConcatBlockLiveins::runOnMachineFunction(llvm::MachineFunction &MF) {
	LLVM_DEBUG(
			dbgs() << "********** ConcatBlockLiveins **********\n"
					<< "********** Function: " << MF.getName() << '\n');
	if (skipFunction(MF.getFunction()))
		return false;
	MachineRegisterInfo &MRI = MF.getRegInfo();
	EdgeLivenessDict livenessPredSuc = hwtHls::getLiveVariablesForBlockEdge(MRI,
			MF);

	MachineLoopInfo &Loops = getAnalysis<MachineLoopInfo>();
	MachineIRBuilder Builder(MF);
	for (MachineBasicBlock &BB : MF) {
		if (!Loops.isLoopHeader(&BB))
			continue;

		SetVector<Register> _liveins;
		for (MachineBasicBlock *PredBB : BB.predecessors()) {
			const auto &liveinsFromBB = livenessPredSuc[PredBB][&BB];
			_liveins.insert(liveinsFromBB.begin(), liveinsFromBB.end());
		}
		if (_liveins.size() > 1) {
			SmallVector<Register> liveins;
			liveins.insert(liveins.end(), _liveins.begin(), _liveins.end());
			sort(liveins);

			size_t newWidth = 0;
			for (Register R : liveins) {
				LLT T = MRI.getType(R);
				assert(T.isValid());
				newWidth += T.getSizeInBits();
			}
			Register liveInReg = MRI.createVirtualRegister(
					&HwtFpga::anyregclsRegClass);
			MRI.setType(liveInReg, LLT::scalar(newWidth));

			Builder.setInsertPt(BB, BB.begin());
			{
				auto newLiveinMO = MachineOperand::CreateReg(liveInReg, true);
				size_t offset = 0;
				for (Register R : liveins) {
					LLT T = MRI.getType(R);
					buildHWTFPGA_EXTRACT(Builder, nullptr, R, newLiveinMO,
							newWidth, offset, T.getSizeInBits());
					offset += T.getSizeInBits();
				}
			}

			for (MachineBasicBlock *PredBB : BB.predecessors()) {
				const auto &liveinsFromBB = livenessPredSuc[PredBB][&BB];
				SmallVector<CImmOrRegOrUndefWithWidth> concatItems;
				for (Register R : liveins) {
					LLT T = MRI.getType(R);
					assert(T.isValid());
					auto w = T.getSizeInBits();
					if (liveinsFromBB.contains(R)) {
						concatItems.push_back(CImmOrRegOrUndefWithWidth(w, R));
					} else {
						concatItems.push_back(CImmOrRegOrUndefWithWidth(w));
					}
				}
				Builder.setInsertPt(*PredBB, PredBB->getFirstTerminator());
				buildHWTFPGA_MERGE_VALUES(Builder, nullptr, liveInReg,
						concatItems);
			}
		}
	}

	return true;
}

INITIALIZE_PASS_BEGIN(ConcatBlockLiveins, DEBUG_TYPE, "ConcatBlockLiveins", false,
		false)
	INITIALIZE_PASS_DEPENDENCY(MachineLoopInfo)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	//INITIALIZE_PASS_END expanded
	PassInfo *PI =
			new PassInfo(
					"Concatenate livein/liveout registers on boundaries into a single register",
					DEBUG_TYPE, &ConcatBlockLiveins::ID,
					PassInfo::NormalCtor_t(callDefaultCtor<ConcatBlockLiveins>),
					false, false);
	Registry.registerPass(*PI, true);
	return PI;
}
static llvm::once_flag InitializeConcatBlockLiveinsFlag;

void initializeConcatBlockLiveins(PassRegistry &Registry) {
	llvm::call_once(InitializeConcatBlockLiveinsFlag,
			hwtHls::initializeConcatBlockLiveinsPassOnce, std::ref(Registry));
}

}
