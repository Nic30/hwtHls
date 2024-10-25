#include <hwtHls/llvm/targets/Transforms/RemovePointerArithmeticPass.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/InitializePasses.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

using namespace llvm;

#define DEBUG_TYPE "hwthls-remove-pointer-arithmetic"

namespace {

class RemovePointerArithmeticPass: public MachineFunctionPass {
	MachineRegisterInfo *MRI;

public:
	static char ID; // Pass identification, replacement for typeid

	RemovePointerArithmeticPass() :
			MachineFunctionPass(ID), MRI(nullptr) {
		initializeRemovePointerArithmeticPassPass(
				*PassRegistry::getPassRegistry());
	}

	void getAnalysisUsage(AnalysisUsage &AU) const override {
		MachineFunctionPass::getAnalysisUsage(AU);
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	MachineFunctionProperties getRequiredProperties() const override {
		MachineFunctionProperties p;
		p.set(MachineFunctionProperties::Property::Legalized); // legalized because this pass generates HwtFpga instructions
		return p;
	}

};

} // end anonymous namespace

char RemovePointerArithmeticPass::ID = 0;

INITIALIZE_PASS(RemovePointerArithmeticPass, DEBUG_TYPE,
		"Remove pointer arithmetic Pass", false, false)

bool RemovePointerArithmeticPass::runOnMachineFunction(MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	bool Changed = false;

	MRI = &MF.getRegInfo();

	// check that any pointer arithmetic is in G_PTR_ADD, G_GLOBAL_VALUE, HWTFPGA_GLOBAL_VALUE, HWTFPGA_ARG_GET
	llvm::SetVector<MachineInstr*> toRemove;
	for (MachineBasicBlock &MBB : MF) {
		for (auto &MI : MBB) {
			if (MI.getOpcode() ==  TargetOpcode::G_PTR_ADD) {
				toRemove.insert(&MI);
			}
		}
	}
	Changed |= toRemove.size();
	while (toRemove.size()) {
		MachineInstr *MI = toRemove.back();
		toRemove.pop_back();
		switch (MI->getOpcode()) {
		case TargetOpcode::G_PHI:
		case HwtFpga::PHI:
		case TargetOpcode::G_PTR_ADD: {
			for (auto& MO: MI->operands()) {
				if (MO.isReg()) {
					if (MO.isDef()) {
						for (auto &Use: MRI->use_instructions(MO.getReg())) {
							if (&Use != MI)
								toRemove.insert(&Use);
						}
					} else {
						for (auto &Def: MRI->def_instructions(MO.getReg())) {
							if (&Def != MI)
								toRemove.insert(&Def);
						}
					}
				}
			}
			MI->eraseFromParent();
			break;
		}
		default:
			break;
		}
	}
	return Changed;
}

namespace hwtHls {
FunctionPass* createRemovePointerArithmeticPass() {
	return new RemovePointerArithmeticPass();
}
}

