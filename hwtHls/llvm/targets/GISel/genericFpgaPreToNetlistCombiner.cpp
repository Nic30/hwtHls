//===----------------------------------------------------------------------===//
//
// This pass does combining of machine instructions at the generic MI level,
// before the to netlist conversion.
//
//===----------------------------------------------------------------------===//
#include "genericFpgaPreToNetlistCombiner.h"
#include "../genericFpgaTargetMachine.h"
#include "../genericFpgaTargetPassConfig.h"

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

#include <llvm/IR/Instructions.h>
#include <llvm/Support/Debug.h>
#include "genericFpgaCombinerHelper.h"

#define DEBUG_TYPE "genericfpga-pretonetlist-combiner"

using namespace llvm;
using namespace MIPatternMatch;

class GenericFpgaGenPreToNetlistGICombinerHelperState {
protected:
	GenFpgaCombinerHelper &Helper;

public:
	GenericFpgaGenPreToNetlistGICombinerHelperState(
			GenFpgaCombinerHelper &Helper) :
			Helper(Helper) {
	}
};

#define GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_DEPS
#include "GenericFpgaGenPreToNetlistGICombiner.inc"
#undef GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_DEPS

namespace {
#define GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_H
#include "GenericFpgaGenPreToNetlistGICombiner.inc"
#undef GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_H

class GenericFpgaPreToNetlistCombinerInfo: public CombinerInfo {
	GISelKnownBits *KB;
	MachineDominatorTree *MDT;
	GenericFpgaGenPreToNetlistGICombinerHelperRuleConfig GeneratedRuleCfg;
public:
	GenericFpgaPreToNetlistCombinerInfo(bool EnableOpt, bool OptSize,
			bool MinSize, GISelKnownBits *KB, MachineDominatorTree *MDT) :
			CombinerInfo(/*AllowIllegalOps*/true, /*ShouldToNetlistIllegal*/
			false,
			/*ToNetlistInfo*/nullptr, EnableOpt, OptSize, MinSize), KB(KB), MDT(
					MDT) {
		if (!GeneratedRuleCfg.parseCommandLineOption())
			report_fatal_error("Invalid rule identifier");
	}

	virtual bool combine(GISelChangeObserver &Observer, MachineInstr &MI,
			MachineIRBuilder &B) const override;

	static void convertGENFPGA_CCOPY_to_GENFPGA_MUX(MachineIRBuilder &Builder);
	static void convertG_SELECT_to_GENFPGA_MUX(MachineIRBuilder &Builder);
	static void convertPHI_to_GENFPGA_MUX(MachineIRBuilder &Builder);
};

void GenericFpgaPreToNetlistCombinerInfo::convertGENFPGA_CCOPY_to_GENFPGA_MUX(
		MachineIRBuilder &Builder) {
	// dst, val, cond
	convertPHI_to_GENFPGA_MUX(Builder);
}

void copyOperand(MachineInstrBuilder &MIB, MachineRegisterInfo &MRI,
		MachineFunction &MF, MachineOperand &MO) {
	if (MO.isReg() && MO.isDef()) {
		MIB.addDef(MO.getReg(), MO.getTargetFlags());
		return;
	} else if (MO.isReg() && MO.getReg()) {
		if (MRI.hasOneDef(MO.getReg())) {
			if (auto VRegVal = getAnyConstantVRegValWithLookThrough(MO.getReg(),
					MRI)) {
				auto &C = MF.getFunction().getContext();
				auto *CI = ConstantInt::get(C, VRegVal->Value);
				MIB.addCImm(CI);
				return;
			}
		}
	}
	MIB.add(MO);
}
void GenericFpgaPreToNetlistCombinerInfo::convertG_SELECT_to_GENFPGA_MUX(
		MachineIRBuilder &Builder) {
	// dst, cond, a, b -> dst, a, cond, b
	MachineInstr &MI = *Builder.getInsertPt();
	MachineInstrBuilder MIB = Builder.buildInstr(GenericFpga::GENFPGA_MUX);
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	if (MI.getNumOperands() != 4) {
		errs() << MI;
		llvm_unreachable("NotImplemented");
	}
	copyOperand(MIB, MRI, MF, MI.getOperand(0));
	copyOperand(MIB, MRI, MF, MI.getOperand(2));
	copyOperand(MIB, MRI, MF, MI.getOperand(1));
	copyOperand(MIB, MRI, MF, MI.getOperand(3));
}

void GenericFpgaPreToNetlistCombinerInfo::convertPHI_to_GENFPGA_MUX(
		MachineIRBuilder &Builder) {
	MachineInstr &MI = *Builder.getInsertPt();
	MachineInstrBuilder MIB = Builder.buildInstr(GenericFpga::GENFPGA_MUX);
	MachineBasicBlock &MBB = *MI.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	for (auto MO : MI.operands()) {
		copyOperand(MIB, MRI, MF, MO);
	}
}

bool GenericFpgaPreToNetlistCombinerInfo::combine(GISelChangeObserver &Observer,
		MachineInstr &MI, MachineIRBuilder &B) const {
	GenFpgaCombinerHelper Helper(Observer, B, KB, MDT);
	GenericFpgaGenPreToNetlistGICombinerHelper Generated(GeneratedRuleCfg,
			Helper);

	if (Generated.tryCombineAll(Observer, MI, B))
		return true;

	unsigned Opc = MI.getOpcode();
	switch (Opc) {
	case TargetOpcode::IMPLICIT_DEF:
	case TargetOpcode::G_IMPLICIT_DEF:
		MI.eraseFromParent();
		return true;
	case TargetOpcode::PHI: {
		std::function<void(llvm::MachineIRBuilder&)> _phiToMux =
				convertPHI_to_GENFPGA_MUX;
		Helper.applyBuildFn(MI, _phiToMux);
		return true;
	}
	case TargetOpcode::G_CONCAT_VECTORS:
		return Helper.tryCombineConcatVectors(MI);
	case TargetOpcode::G_SHUFFLE_VECTOR:
		return Helper.tryCombineShuffleVector(MI);
	case TargetOpcode::G_MEMCPY_INLINE:
		return Helper.tryEmitMemcpyInline(MI);
	case llvm::GenericFpga::GENFPGA_CCOPY: {
		std::function<void(llvm::MachineIRBuilder&)> _ccopyToMux =
				convertGENFPGA_CCOPY_to_GENFPGA_MUX;
		Helper.applyBuildFn(MI, _ccopyToMux);
		return true;
	}
	case llvm::GenericFpga::G_SELECT:
		std::function<void(llvm::MachineIRBuilder&)> _selectToMux =
				convertG_SELECT_to_GENFPGA_MUX;
		Helper.applyBuildFn(MI, _selectToMux);
		return true;
	}

	return false;
}

#define GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_CPP
#include "GenericFpgaGenPreToNetlistGICombiner.inc"
#undef GENERICFPGAGENPRETONETLISTGICOMBINERHELPER_GENCOMBINERHELPER_CPP

// Pass boilerplate
// ================

class GenericFpgaPreToNetlistCombiner: public MachineFunctionPass {
public:
	static char ID;
	GenericFpgaPreToNetlistCombiner();

	StringRef getPassName() const override {
		return "GenericFpgaPreToNetlistCombiner";
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	void getAnalysisUsage(AnalysisUsage &AU) const override;
};
} // end anonymous namespace

void GenericFpgaPreToNetlistCombiner::getAnalysisUsage(
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

GenericFpgaPreToNetlistCombiner::GenericFpgaPreToNetlistCombiner() :
		MachineFunctionPass(ID) {
	initializeGenericFpgaPreToNetlistCombinerPass(
			*PassRegistry::getPassRegistry());
}

bool GenericFpgaPreToNetlistCombiner::runOnMachineFunction(
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
	GenericFpgaPreToNetlistCombinerInfo PCInfo(EnableOpt, F.hasOptSize(),
			F.hasMinSize(), KB, MDT);
	Combiner C(PCInfo, &TPC);

	return C.combineMachineInstrs(MF, CSEInfo);
}

char GenericFpgaPreToNetlistCombiner::ID = 0;
INITIALIZE_PASS_BEGIN(GenericFpgaPreToNetlistCombiner, DEBUG_TYPE,
		"Combine GenericFpga machine instrs before to netlist conversion",
		false, false)
	INITIALIZE_PASS_DEPENDENCY(TargetPassConfig)
	INITIALIZE_PASS_DEPENDENCY(GISelKnownBitsAnalysis)
	INITIALIZE_PASS_DEPENDENCY(GISelCSEAnalysisWrapperPass)
	INITIALIZE_PASS_END(GenericFpgaPreToNetlistCombiner, DEBUG_TYPE,
			"Combine GenericFpga machine instrs before to netlist conversion",
			false, false)

namespace llvm {

FunctionPass* createGenericFpgaPreToNetlistCombiner() {
	return new GenericFpgaPreToNetlistCombiner();
}

} // end namespace llvm
