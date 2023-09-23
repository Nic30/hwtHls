#include <hwtHls/llvm/targets/GISel/hwtFpgaCallLoweringInfo.h>

#include <hwtHls/llvm/targets/hwtFpgaTargetLowering.h>
#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/Utils.h>
#include <llvm/Support/Casting.h>

#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#include <iostream>

namespace llvm {

HwtFpgaCallLowering::HwtFpgaCallLowering(
		const llvm::HwtFpgaTargetLowering &TLI) :
		llvm::CallLowering(&TLI) {
}

bool HwtFpgaCallLowering::lowerReturn(MachineIRBuilder &MIRBuilder,
		const Value *Val, ArrayRef<Register> VRegs,
		FunctionLoweringInfo &FLI) const {

	MachineInstrBuilder Ret = MIRBuilder.buildInstrNoInsert(
			HwtFpga::PseudoRET);
	if (Val != nullptr) {
		return false;
	}
	MIRBuilder.insertInstr(Ret);
	return true;
}

bool HwtFpgaCallLowering::lowerFormalArguments(MachineIRBuilder &MIRBuilder,
		const Function &F, ArrayRef<ArrayRef<Register>> VRegs,
		FunctionLoweringInfo &FLI) const {
	if (F.arg_empty())
		throw std::runtime_error(
				"HwtFpgaCallLowering::lowerFormalArguments is meant for functions realized in hardware,"
						" args. represents IO, this function does not have any.");
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

		//unsigned SrcReg = HwtFpga::DUMMY_REG_0 + Arg.getArgNo();
		assert(VRegs[Arg.getArgNo()].size() == 1);
		unsigned DstReg = VRegs[Arg.getArgNo()][0]; // we must reuse prepared argument register
		MRI.setType(DstReg, LLT::pointer(i, 64));
		MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);

		///MRI.addLiveIn(SrcReg, DstReg);
		MachineInstrBuilder MIB = MIRBuilder.buildInstr(
				HwtFpga::HWTFPGA_ARG_GET);
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

bool HwtFpgaCallLowering::lowerCall(MachineIRBuilder &MIRBuilder,
		CallLoweringInfo &Info) const {
	auto *F = dyn_cast_or_null<Function>(Info.Callee.getGlobal());
	MachineRegisterInfo &MRI = *MIRBuilder.getMRI();
	if (F) {
		if (hwtHls::IsBitConcat(F)) {
			// BitConcat has higher bits first
			assert(Info.OrigRet.Regs.size() == 1);
			unsigned DstReg = Info.OrigRet.Regs[0];
			auto MBI = MIRBuilder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES)	// lower bits first
			.addReg(DstReg, RegState::Define);
			MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);
			// add operands
			//bool first = true;
			for (auto &op : Info.OrigArgs) {
				//assert(op.Regs.size() == 1);
				//if (first) {
				//	// skip first item because it is destination which was already added
				//	first = false;
				//	continue;
				//}
				MBI.addUse(op.Regs[0]);
			}
			// add operand widths
			//first = true;
			for (auto &op : Info.OrigArgs) {
				//assert(op.Regs.size() == 1);
				//if (first) {
				//	// skip first item because it is destination which was already added
				//	first = false;
				//	continue;
				//}
				uint64_t width = MRI.getType(op.Regs[0]).getSizeInBits();
				MBI.addImm(width);
			}
			return true;
		} else if (hwtHls::IsBitRangeGet(F)) {
			assert(Info.OrigRet.Regs.size() == 1);
			// dst, src, offset in bits (same in BitRangeGet and G_EXTRACT), offset must be imm
			auto MIB = MIRBuilder.buildInstr(TargetOpcode::G_EXTRACT)	 //
			.addReg(Info.OrigRet.Regs[0], RegState::Define);

			MIB.addUse(Info.OrigArgs[0].Regs[0]);
			Register offset = Info.OrigArgs[1].Regs[0];

			assert(MRI.hasOneDef(offset) && "SSA expected");
			if (std::optional<ValueAndVReg> VRegVal =
					getAnyConstantVRegValWithLookThrough(offset,
							*MIRBuilder.getMRI())) {
				auto offsetVal = VRegVal.value().Value;
				assert(offsetVal.isNonNegative());
				MIB.addImm(VRegVal.value().Value.getZExtValue());
			} else {
				throw std::runtime_error(
						"hwtHls.bitRangeGet offset operand must be constant");
			}
			return true;
		} else {
			throw std::runtime_error(
					"Not implemented, call of generic function in HW function");
		}
	}
	throw std::runtime_error("Not implemented, lowerCall");
	return false;
}

bool HwtFpgaCallLowering::canLowerReturn(MachineFunction &MF,
		CallingConv::ID CallConv, SmallVectorImpl<BaseArgInfo> &Outs,
		bool IsVarArg) const {
	//assert(Outs.size() == 0 && "HwtFpgaCallLowering::canLowerReturn should be used only for HW functions which do have only void return type.");
	return true;
}

}
