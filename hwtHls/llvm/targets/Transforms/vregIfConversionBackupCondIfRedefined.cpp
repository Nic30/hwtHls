#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/Support/ErrorHandling.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

using namespace llvm;

namespace hwtHls {

void VRegIfConverter::backupCondIfRedefined(
	BBInfo &BBI, BBInfo &NewSucBBI, SmallVector<MachineOperand, 4> &Cond) {
	if (Cond.empty())
		return; // no condition at all

	if (Cond.size() != 2)
		llvm_unreachable("backupCondIfRedefined implemented only for cond in "
						 "format (condOp, isNegatedImm)");

	assert(Cond[1].isImm());
	if (!Cond[0].isReg()) {
		// condition is constant
		assert(Cond[0].isCImm());
		return;
	}

	Register C = Cond[0].getReg();
	bool sucRedefinesCondReg = false;
	for (auto &defMI : MRI->def_instructions(C)) {
		if (defMI.getParent() == NewSucBBI.BB) {
			sucRedefinesCondReg = true;
			break;
		}
	}
	if (!sucRedefinesCondReg)
		return; // no need to backup condition

	auto insertBefore = BBI.BB->getFirstTerminator();
	auto newC = MRI->cloneVirtualRegister(C);
	MachineIRBuilder Builder(*BBI.BB, insertBefore);
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
	MIB.addDef(newC);
	MIB.addUse(C);
	Cond[0] = MachineOperand::CreateReg(newC, true);
}

}