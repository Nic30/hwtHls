#include "genericFpgaCallLoweringInfo.h"
#include "../genericFpgaTargetLowering.h"
#include "../genericFpgaRegisterInfo.h"
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include "../intrinsic/bitrange.h"

#include <iostream>

namespace llvm {

GenericFpgaCallLowering::GenericFpgaCallLowering(
		const llvm::GenericFpgaTargetLowering &TLI) :
		llvm::CallLowering(&TLI) {
}

bool GenericFpgaCallLowering::lowerReturn(MachineIRBuilder &MIRBuilder,
		const Value *Val, ArrayRef<Register> VRegs,
		FunctionLoweringInfo &FLI) const {

	MachineInstrBuilder Ret = MIRBuilder.buildInstrNoInsert(GenericFpga::PseudoRET);
	if (Val != nullptr) {
	  return false;
	}
	MIRBuilder.insertInstr(Ret);
	return true;
}

bool GenericFpgaCallLowering::lowerFormalArguments(MachineIRBuilder &MIRBuilder,
		const Function &F, ArrayRef<ArrayRef<Register>> VRegs,
		FunctionLoweringInfo &FLI) const {
	if (F.arg_empty())
		llvm_unreachable(
				"GenericFpgaCallLowering::lowerFormalArguments is meant for functions realized in hardware,"
				" args. represents IO and there must be some IO.");

	MachineFunction &MF = MIRBuilder.getMF();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	const DataLayout &DL = MF.getDataLayout();
	//const auto * TII = MF.getSubtarget().getInstrInfo();
	unsigned i = 0;
	// based on ARMFastISel::fastLowerArguments() but modified for GlobalISel
	for (const Argument &Arg : F.args()) {
		ArgInfo AInfo(VRegs[i], Arg, i);
		setArgFlags(AInfo, i + AttributeList::FirstArgIndex, DL, F);
		++i;

		//unsigned SrcReg = GenericFpga::DUMMY_REG_0 + Arg.getArgNo();
		assert(VRegs[Arg.getArgNo()].size() == 1);
		unsigned DstReg = VRegs[Arg.getArgNo()][0]; // we must reuse prepared argument register
		MRI.setType(DstReg, LLT::pointer(i, 64));
		MRI.setRegClass(DstReg, &GenericFpga::AnyRegClsRegClass);

		///MRI.addLiveIn(SrcReg, DstReg);
		MachineInstrBuilder MIB = MIRBuilder.buildInstr(GenericFpga::GENFPGA_ARG_GET);
		MIB.addDef(DstReg).addImm(i - 1);
		//MRI.setType(SrcReg, LLT::pointer(i, 64));
		//MRI.setType(DstReg, LLT::pointer(i, 64));
		// FIXME: Unfortunately it's necessary to emit a copy from the livein copy.
		// Without this, EmitLiveInCopies may eliminate the livein if its only
		// use is a bitcast (which isn't turned into an instruction).
		//MIRBuilder.buildInstr(TargetOpcode::COPY)		//
		//.addReg(DstReg, RegState::Define)	 //
		//.addReg(SrcReg, getKillRegState(true));
	}

	return true;
}

bool GenericFpgaCallLowering::lowerCall(MachineIRBuilder &MIRBuilder,
		CallLoweringInfo &Info) const {
	auto *F = dyn_cast_or_null<llvm::Function>(Info.Callee.getGlobal());
	if (F) {
		if (IsBitConcat(F)) {
			assert(Info.OrigRet.Regs.size() == 1);
			auto MBI = MIRBuilder.buildInstr(TargetOpcode::G_MERGE_VALUES)	 //
			.addReg(Info.OrigRet.Regs[0], RegState::Define);
			bool first = true;
			for (ArgInfo &op : Info.OrigArgs) {
				assert(op.Regs.size() == 1);
				if (first) {
					first = false;
					continue;
				}
				MBI.addUse(op.Regs[0]);
			}
			return true;
		} else if (IsBitRangeGet(F)) {
			assert(Info.OrigRet.Regs.size() == 1);
			auto MBI = MIRBuilder.buildInstr(TargetOpcode::G_EXTRACT)	 //
			.addReg(Info.OrigRet.Regs[0], RegState::Define);
			// dst, src, offset in bits (same in BitRangeGet and G_EXTRACT)
			bool first = true;
			for (ArgInfo &op : Info.OrigArgs) {
				assert(op.Regs.size() == 1);
				if (first) {
					first = false;
					continue;
				}
				MBI.addUse(op.Regs[0]);
			}
			return true;
		} else {
			llvm_unreachable(
					"Not implemented, call of generic function in HW function");
		}
	}
	llvm_unreachable("Not implemented, lowerCall");
	return false;
}

bool GenericFpgaCallLowering::canLowerReturn(MachineFunction &MF,
		CallingConv::ID CallConv, SmallVectorImpl<BaseArgInfo> &Outs,
		bool IsVarArg) const {
	//assert(Outs.size() == 0 && "GenericFpgaCallLowering::canLowerReturn should be used only for HW functions which do have only void return type.");
	return false;
}

}
