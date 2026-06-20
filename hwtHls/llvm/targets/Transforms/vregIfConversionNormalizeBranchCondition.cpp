#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

using namespace llvm;

namespace hwtHls {

bool VRegIfConverter::normalizeBranchCondition(VRegIfConverter::BBInfo &BBI,
											   bool unnegateConditions) {
	MachineBasicBlock &MBB = *BBI.BB;
	bool changed = false;
	if (BBI.TrueBB) {
		assert(BBI.TrueBB->getNumber() >= 0);
	} else {
		return changed;
	}
	if (BBI.FalseBB) {
		assert(BBI.FalseBB->getNumber() >= 0);
	} else {
		return changed;
	}
	auto &br = *MBB.terminators().begin();
	assert(&br && br.isConditionalBranch());
	if (BBI.TrueBB == BBI.FalseBB) {
		DebugLoc DL = MBB.getFirstTerminator()->getDebugLoc();
		TII->removeBranch(MBB);
		TII->insertUnconditionalBranch(MBB, BBI.TrueBB, DL);
		BBI.FalseBB = nullptr;
		BBI.BrCond.clear();
		changed = true;
	} else if (unnegateConditions) {
		auto &c = br.getOperand(0);
		assert(c.isReg());
		bool wasKill;
		bool reverse =
			getRegisterNegationIfExits(*MRI, TRI, MBB, MBB.end(), c.getReg(),
									   wasKill) != nullptr;
		if (reverse && reverseBranchCondition(BBI)) {
			changed = true;
			if (BBI.TrueBB)
				assert(BBI.TrueBB->getNumber() >= 0);
			if (BBI.FalseBB)
				assert(BBI.FalseBB->getNumber() >= 0);
			if (VRegLiveins)
				VRegLiveins->UpdateKillAndDeadFlags(*BBI.BB);
		}
	}

	return changed;
}

bool VRegIfConverter::normalizeBranchConditions(MachineFunction &MF,
												bool unnegateConditions) {
	bool Changed = false;
	for (auto &MB : MF) {
		VRegIfConverter::BBInfo BBI;
		BBI.BB = &MB;
		if (MB.getNumber() < 0)
			continue;
		if (!TII->analyzeBranch(*BBI.BB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond)) {
			if (!BBI.TrueBB)
				continue;
			assert(BBI.TrueBB->getNumber() >= 0);
			if (!BBI.FalseBB) {
				BBI.FalseBB = findFalseBlock(BBI.BB, BBI.TrueBB);
			}
			Changed |= normalizeBranchCondition(BBI, unnegateConditions);
		}
	}
	return Changed;
}

}
