#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>

namespace llvm {

bool HwtFpgaCombinerHelper::isTrivialRemovableCopy(llvm::MachineInstr &MI,
		bool &replaceMuxSrcReg) {

	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	if (MI.getNumOperands() != 1 + 1)
		return false;

	auto &src = MI.getOperand(1);
	if (!src.isReg()) {
		// no need to propagate constants in this function
		return false;
	}
	auto srcReg = src.getReg();
	auto dstReg = MI.getOperand(0).getReg();

	if (src.isReg() && MRI.hasOneUse(dstReg)) {
		auto def = MRI.getOneDef(srcReg);
		if (def && def->getParent()->getParent() == MI.getParent()
				&& isPredecessor(*def->getParent(), MI)) {
			/*
			 * Check for
			 *  %src = ...
			 *  ... <anything not not having %dst as operand> (because if we replace dst<-src the dst would have the copied variant which was not intended)
			 *  %dst = HWTFPGA_MUX %src
			 *
			 *  to later replace it with just %0 (replaceMuxSrcReg=true)
			 * */
			auto *defInstr = def->getParent();
			auto i = defInstr->getNextNode();
			while (i) {
				if (i == &MI) {
					replaceMuxSrcReg = true;
					return true;
				}
				bool dstRegUsedOrModified = false;
				for (auto &MO : i->operands()) {
					if (MO.isReg() && MO.getReg() == dstReg) {
						dstRegUsedOrModified = true;
						break;
					}
				}
				if (dstRegUsedOrModified)
					break;
				i = i->getNextNode();
			}
		}
	}

	// try to find a single user of copy mux dst register
	MachineInstr *user = nullptr;
	for (auto &u : MRI.use_operands(dstReg)) {
		if (user == nullptr) {
			// search if dstReg is modified or srcReg is modified
			user = u.getParent();
			if (user->getParent() != MI.getParent())
				return false; // can replace only inside of the same block
		}
		// check that there is only single user instruction (allow use in multiple operands)
		if (user != u.getParent()) {
			return false;
		} else if (isPredecessor(*user, *u.getParent())) {
			user = u.getParent(); // get latest user
		}
	}
	if (user) {
		/*
		 * check that it is possible to replace mux src register with dstRegister
		 *  %dst = HWTFPGA_MUX %src
		 *  ... <anything not not having %0 and %1 as dst operand>
		 *  use(%dst) # only use of %dst
		 *  to later replace with use(%src) (replaceMuxSrcReg=false)
		 **/
		if (!isPredecessor(MI, *user)) {
			return false;
		}
		auto i = MI.getNextNode();
		while (i) {
			if (i == user) {
				// we successfully got on user instruction, it means that it is safe to replace
				break;
			}
			for (auto &MO : i->operands()) {
				if (MO.isReg()) {
					auto r = MO.getReg();
					if (MO.isDef()) {
						if (r == srcReg || r == dstReg) {
							return false;
						}
					}
				}
			}
			i = i->getNextNode();
		}

		// replace dstReg with srcReg
		replaceMuxSrcReg = false;
		return true;
	}
	return false;
}

bool HwtFpgaCombinerHelper::rewriteTrivialRemovableCopy(llvm::MachineInstr &MI,
		bool replaceMuxSrcReg) {
	auto &dst = MI.getOperand(0);
	auto &src = MI.getOperand(1);
	auto srcReg = src.getReg();
	auto dstReg = dst.getReg();

	Register fromReg, toReg;
	if (replaceMuxSrcReg) {
		// replace src reg with dst reg
		fromReg = srcReg;
		toReg = dstReg;
	} else {
		fromReg = dstReg;
		toReg = srcReg;
	}
	SmallVector<MachineOperand*> toReplace;
	for (auto &def : MRI.def_operands(fromReg)) {
		if (def.getParent() != &MI)
			toReplace.push_back(&def);
	}
	for (auto &u : MRI.use_operands(fromReg)) {
		if (u.getParent() != &MI)
			toReplace.push_back(&u);
	}
	for (auto *u : toReplace) {
		//errs() << "replace dst " << u->getReg().virtRegIndex() << "->" << dstReg.virtRegIndex() << "\n";
		u->setReg(toReg);
	}

	MI.eraseFromParent();
	return true;
}

}
