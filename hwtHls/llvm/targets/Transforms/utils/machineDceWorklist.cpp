#include <hwtHls/llvm/targets/Transforms/utils/machineDceWorklist.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>

using namespace llvm;

namespace hwtHls {

bool isMachineInstructionTriviallyDead(MachineInstr &MI) {
	if (MI.isDebugInstr() || MI.isDebugValue())
		return false;
	if (MI.isBarrier() || MI.isBranch() || MI.hasUnmodeledSideEffects()
			|| MI.isTerminator())
		return false;
	for (auto MO : MI.memoperands()) {
		if (MO->isVolatile())
			return false;
	}
	for (auto DefMO : MI.defs()) {
		if (!DefMO.isDead())
			return false;
	}
	return true;
}

// copied from llvm/lib/Transforms/Scalar/DCE.cpp modified for Machine IR
bool MachineDCEInstruction(MachineDceWorklist &DCE, MachineRegisterInfo &MRI,
		LiveVRegs *liveVregs, MachineInstr &MI,
		SmallSetVector<MachineInstr*, 16> &WorkList) {
	if (isMachineInstructionTriviallyDead(MI)) {
		// Null out all of the instruction's operands to see if any operand becomes
		// dead as we go.
		for (auto &UMO : MI.uses()) {
			Register DummyReg = 0;
			if (!UMO.isReg())
				continue;

			Register R = UMO.getReg();
			UMO.ChangeToRegister(DummyReg, false);
			DCE.insert(R);
		}
		if (liveVregs)
			for (auto &Def : MI.defs()) {
				if (MRI.def_empty(Def.getReg())) {
					liveVregs->removeReg(Def.getReg());
				}
			}
		MI.eraseFromParent();
		return true;
	}
	return false;
}

bool MachineDceWorklist::empty() const {
	return WorkList.empty();
}

void MachineDceWorklist::insert(llvm::MachineInstr &MI) {
	if (!WorkList.count(&MI))
		WorkList.insert(&MI);
}

void MachineDceWorklist::insert(Register R) {
	if (!MRI.use_empty(R))
		return;

	// If the operand is an instruction that became dead as we nulled out the
	// operand, and if it is 'trivially' dead, delete it in a future loop
	// iteration.
	for (MachineOperand &DefOp : MRI.def_operands(R)) {
		DefOp.setIsDead();
		auto &DefI = *DefOp.getParent();
		if (isMachineInstructionTriviallyDead(DefI))
			WorkList.insert(&DefI);
	}
}

bool MachineDceWorklist::tryRemoveIfDead(llvm::MachineInstr &MI) {
	if (!WorkList.count(&MI)) {
		return MachineDCEInstruction(*this, MRI, liveVregs, MI, WorkList);
	}
	return false;
}

bool MachineDceWorklist::runToCompletition() {
	bool MadeChange = false;
	while (!WorkList.empty()) {
		MachineInstr *MI = WorkList.pop_back_val();
		MadeChange |= MachineDCEInstruction(*this, MRI, liveVregs, *MI, WorkList);
	}
	return MadeChange;
}

}
