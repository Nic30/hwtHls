#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

using namespace llvm;

namespace hwtHls {

bool VRegIfConverter::normalizeBranchCondition(VRegIfConverter::BBInfo &BBI) {
	MachineBasicBlock &MBB = *BBI.BB;
	bool reverse = false;
	if (BBI.TrueBB)
		assert(BBI.TrueBB->getNumber() >= 0);
	if (BBI.FalseBB)
		assert(BBI.FalseBB->getNumber() >= 0);

	if (MBB.succ_size() == 2) {
		auto &br = *MBB.terminators().begin();
		assert(&br && br.isConditionalBranch());
		auto &c = br.getOperand(0);
		assert(c.isReg());
		bool wasKill;
		reverse = getRegisterNegationIfExits(*MRI, MBB, MBB.end(), c.getReg(), wasKill) != nullptr;
	}
	if (reverse) {
		reverse &= reverseBranchCondition(BBI);
		if (BBI.TrueBB)
			assert(BBI.TrueBB->getNumber() >= 0);
		if (BBI.FalseBB)
			assert(BBI.FalseBB->getNumber() >= 0);
		if (VRegLiveins)
			VRegLiveins->UpdateKillAndDeadFlags(*BBI.BB);
	}

	return reverse;
}

bool VRegIfConverter::normalizeBranchConditions(MachineFunction & MF) {
	bool Changed = false;
	for (auto &MB: MF) {
		VRegIfConverter::BBInfo BBI;
		BBI.BB = &MB;
		if (MB.getNumber() < 0)
			continue;
		if(MB.succ_size() == 2 && !TII->analyzeBranch(*BBI.BB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond)) {
			assert(BBI.TrueBB->getNumber() >= 0);
			if (!BBI.FalseBB) {
				BBI.FalseBB = findFalseBlock(BBI.BB, BBI.TrueBB);
				assert(BBI.FalseBB);
			} else {
				assert(BBI.FalseBB->getNumber() >= 0);
			}
			Changed |= normalizeBranchCondition(BBI);
			assert(BBI.TrueBB->getNumber() >= 0);
			assert(BBI.FalseBB->getNumber() >= 0);
		}
	}
	return Changed;
}

}
