//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the to netlist conversion.
//
//===----------------------------------------------------------------------===//
#include <hwtHls/llvm/targets/GISel/hwtFpgaPreToNetlistCombiner.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

#include <llvm/CodeGen/GlobalISel/Combiner.h>
#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <llvm/CodeGen/GlobalISel/CombinerInfo.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/CodeGen/GlobalISel/CombinerHelper.h>
#include <llvm/CodeGen/GlobalISel/CSEInfo.h>

#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#define DEBUG_TYPE "hwtfpga-pretonetlist-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class HwtFpgaGenPreToNetlistGICombinerHelperState {
protected:
	HwtFpgaCombinerHelper &Helper;

public:
	HwtFpgaGenPreToNetlistGICombinerHelperState(
			HwtFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "HwtFpgaGenPreToNetlistGICombiner.inc"
#undef HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "HwtFpgaGenPreToNetlistGICombiner.inc"
#undef HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_H

class HwtFpgaPreToNetlistCombinerInfo: public CombinerInfo {
	bool isPrelegalize;
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	HwtFpgaGenPreToNetlistGICombinerHelperRuleConfig GeneratedRuleCfg;
public:
	HwtFpgaPreToNetlistCombinerInfo(bool EnableOpt, bool OptSize,
			bool MinSize, bool isPrelegalize, GISelKnownBits *KB,
			MachineDominatorTree *MDT, const LegalizerInfo *LInfo) :
			CombinerInfo(/*AllowIllegalOps*/true, /*ShouldToNetlistIllegal*/
			false, LInfo, EnableOpt, OptSize, MinSize), isPrelegalize(
					isPrelegalize), KB(KB), MDT(MDT) {
		if (!GeneratedRuleCfg.parseCommandLineOption())
			report_fatal_error("Invalid rule identifier");
	}

	virtual bool combine(GISelChangeObserver &Observer, MachineInstr &MI,
			MachineIRBuilder &B) const override;

	static void convertG_SELECT_to_HWTFPGA_MUX(MachineIRBuilder &Builder);
	static void convertPHI_to_HWTFPGA_MUX(MachineIRBuilder &Builder);
};

void copyOperand(MachineInstrBuilder &MIB, MachineRegisterInfo &MRI,
		MachineFunction &MF, MachineOperand &MO) {
	if (MO.isReg() && MO.isDef()) {
		MIB.addDef(MO.getReg(), MO.getTargetFlags());
		return;
	} else if (MO.isReg() && MO.getReg() && MRI.hasOneDef(MO.getReg())) {
		if (auto VRegVal = getAnyConstantVRegValWithLookThrough(MO.getReg(),
				MRI)) {
			auto &C = MF.getFunction().getContext();
			auto *CI = ConstantInt::get(C, VRegVal->Value);
			MIB.addCImm(CI);
			return;
		}
	}
	MIB.add(MO);
}

void HwtFpgaPreToNetlistCombinerInfo::convertG_SELECT_to_HWTFPGA_MUX(
		MachineIRBuilder &Builder) {
	// dst, cond, a, b -> dst, a, cond, b
	MachineInstr &MI = *Builder.getInsertPt();
	MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	if (MI.getNumOperands() != 4) {
		errs() << MI;
		llvm_unreachable("NotImplemented");
	}
	copyOperand(MIB, MRI, MF, MI.getOperand(0)); // dst
	copyOperand(MIB, MRI, MF, MI.getOperand(2)); // v0
	copyOperand(MIB, MRI, MF, MI.getOperand(1)); // cond
	copyOperand(MIB, MRI, MF, MI.getOperand(3)); // v1s
}

void HwtFpgaPreToNetlistCombinerInfo::convertPHI_to_HWTFPGA_MUX(
		MachineIRBuilder &Builder) {
	MachineInstr &MI = *Builder.getInsertPt();
	MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	for (auto MO : MI.operands()) {
		copyOperand(MIB, MRI, MF, MO);
	}
}

bool HwtFpgaPreToNetlistCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	HwtFpgaCombinerHelper Helper(Observer, B, false, KB, MDT, LInfo);
	HwtFpgaGenPreToNetlistGICombinerHelper Generated(GeneratedRuleCfg,
			Helper);

	if (Generated.tryCombineAll(Observer, MI, B))
		return true;

	unsigned Opc = MI.getOpcode();
	switch (Opc) {
	//case TargetOpcode::IMPLICIT_DEF:
	//case TargetOpcode::G_IMPLICIT_DEF:
	//	MI.eraseFromParent();
	//	return true;
	case TargetOpcode::PHI: {
		std::function<void(llvm::MachineIRBuilder&)> _phiToMux =
				convertPHI_to_HWTFPGA_MUX;
		Helper.applyBuildFn(MI, _phiToMux);
		return true;
	}
	case TargetOpcode::G_CONCAT_VECTORS:
		return Helper.tryCombineConcatVectors(MI);
	case TargetOpcode::G_SHUFFLE_VECTOR:
		return Helper.tryCombineShuffleVector(MI);
	case TargetOpcode::G_MEMCPY_INLINE:
		return Helper.tryEmitMemcpyInline(MI);
	case llvm::HwtFpga::G_SELECT:
		std::function<void(llvm::MachineIRBuilder&)> _selectToMux =
				convertG_SELECT_to_HWTFPGA_MUX;
		Helper.applyBuildFn(MI, _selectToMux);
		return true;
	}

	return false;
}

#define HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "HwtFpgaGenPreToNetlistGICombiner.inc"
#undef HWTFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_CPP

// Pass boilerplate
// ================

class HwtFpgaPreToNetlistCombiner: public MachineFunctionPass {
public:
	static char ID;
	HwtFpgaPreToNetlistCombiner();

	StringRef getPassName() const override {
		return "HwtFpgaPreToNetlistCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	void getAnalysisUsage(AnalysisUsage &AU) const override;
};
} // end anonymous namespace

void HwtFpgaPreToNetlistCombiner::getAnalysisUsage(
		AnalysisUsage &AU) const {
	AU.addRequired<TargetPassConfig>();
	AU.setPreservesCFG();
	getSelectionDAGFallbackAnalysisUsage(AU);
	AU.addRequired<GISelKnownBitsAnalysis>();
	AU.addPreserved<GISelKnownBitsAnalysis>();
	AU.addRequired<MachineDominatorTree>();
	AU.addPreserved<MachineDominatorTree>();
	AU.addRequired<GISelCSEAnalysisWrapperPass>();
	AU.addPreserved<GISelCSEAnalysisWrapperPass>();
	MachineFunctionPass::getAnalysisUsage(AU);
}

HwtFpgaPreToNetlistCombiner::HwtFpgaPreToNetlistCombiner() :
		MachineFunctionPass(ID) {
	initializeHwtFpgaPreToNetlistCombinerPass(
			*PassRegistry::getPassRegistry());
}

bool HwtFpgaPreToNetlistCombiner::runOnMachineFunction(
		MachineFunction &MF) {
	if (MF.getProperties().hasProperty(
			MachineFunctionProperties::Property::FailedISel))
		return false;
	auto &TPC = getAnalysis<TargetPassConfig>();

	// Enable CSE.
	GISelCSEAnalysisWrapper &Wrapper =
			getAnalysis<GISelCSEAnalysisWrapperPass>().getCSEWrapper();
	auto *CSEInfo = &Wrapper.get(TPC.getCSEConfig());

	const Function &F = MF.getFunction();
	bool EnableOpt = MF.getTarget().getOptLevel() != CodeGenOpt::None
			&& !skipFunction(F);
	GISelKnownBits *KB = &getAnalysis<GISelKnownBitsAnalysis>().get(MF);
	MachineDominatorTree *MDT = &getAnalysis<MachineDominatorTree>();
	const LegalizerInfo *LInfo = ((const HwtFpgaTargetSubtarget *)&MF.getSubtarget())->getLegalizerInfo();
	HwtFpgaPreToNetlistCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), false, KB, MDT, LInfo);
	Combiner C(PCInfo, &TPC);

	return C.combineMachineInstrs(MF, CSEInfo);
}

char HwtFpgaPreToNetlistCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(HwtFpgaPreToNetlistCombiner, DEBUG_TYPE,
		"Combine HwtFpga machine instrs before to netlist conversion",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(HwtFpgaPreToNetlistCombiner, DEBUG_TYPE,
			"Combine HwtFpga machine instrs before to netlist conversion",
			false, false)

namespace llvm {

FunctionPass* createHwtFpgaPreToNetlistCombiner() {
	return new HwtFpgaPreToNetlistCombiner();
}

} // end namespace llvm
