#include <hwtHls/llvm/targets/GISel/hwtFpgaCallLoweringInfo.h>

#include <hwtHls/llvm/targets/hwtFpgaTargetLowering.h>
#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/Utils.h>
#include <llvm/Support/Casting.h>
#include <llvm/IR/Attributes.h>

#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/hfloattmp.h>
#include <hwtHls/llvm/targets/intrinsic/pyObjectPlaceholder.h>

#include <iostream>

namespace llvm {

HwtFpgaCallLowering::HwtFpgaCallLowering(const llvm::HwtFpgaTargetLowering &TLI) :
		llvm::CallLowering(&TLI) {
}

bool HwtFpgaCallLowering::lowerReturn(MachineIRBuilder &MIRBuilder,
		const Value *Val, ArrayRef<Register> VRegs,
		FunctionLoweringInfo &FLI) const {

	MachineInstrBuilder Ret = MIRBuilder.buildInstrNoInsert(HwtFpga::HWTFPGA_RET);
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

bool addIntImmByRegiter(MachineRegisterInfo &MRI, MachineInstrBuilder &MIB,
		Register objId) {
	assert(MRI.hasOneDef(objId) && "SSA expected");
	if (std::optional<ValueAndVReg> VRegVal =
			getAnyConstantVRegValWithLookThrough(objId, MRI)) {
		auto objIdVal = VRegVal.value().Value;
		MIB.addImm(VRegVal.value().Value.getZExtValue());
		return true;
	} else {
		return false;
	}
}

bool HwtFpgaCallLowering::lowerCall(MachineIRBuilder &MIRBuilder,
		CallLoweringInfo &Info) const {
	const Function *F = dyn_cast_or_null<Function>(Info.Callee.getGlobal());
	MachineRegisterInfo &MRI = *MIRBuilder.getMRI();
	if (F) {
		if (hwtHls::IsBitConcat(F)) {
			// BitConcat has higher bits first
			assert(Info.OrigRet.Regs.size() == 1);
			unsigned DstReg = Info.OrigRet.Regs[0];
			auto MIB = MIRBuilder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES)	// lower bits first
			.addReg(DstReg, RegState::Define);
			MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);
			// add operands
			for (auto &op : Info.OrigArgs) {
				MIB.addUse(op.Regs[0]);
			}
			// add operand widths
			for (auto &op : Info.OrigArgs) {
				uint64_t width = MRI.getType(op.Regs[0]).getSizeInBits();
				MIB.addImm(width);
			}
			return true;

		} else if (hwtHls::IsBitRangeGet(F)) {
			assert(Info.OrigRet.Regs.size() == 1);
			// dst, src, offset in bits (same in BitRangeGet and G_EXTRACT), offset must be imm
			auto DstReg = Info.OrigRet.Regs[0];
			auto MIB = MIRBuilder.buildInstr(TargetOpcode::G_EXTRACT)	 //
			.addReg(DstReg, RegState::Define);
			MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);

			MIB.addUse(Info.OrigArgs[0].Regs[0]);
			Register offset = Info.OrigArgs[1].Regs[0];
			if (!addIntImmByRegiter(MRI, MIB, offset)) {
				std::string errStr =
						"hwtHls.bitRangeGet offset operand must be constant: ";
				llvm::raw_string_ostream ss(errStr);
				Info.CB->print(ss);
				throw std::runtime_error(ss.str());
			}
			return true;

		} else if (hwtHls::IsPyObjectPlacehoder(F)) {
			bool noDuplicate = Info.CB->hasFnAttr(
					Attribute::AttrKind::NoDuplicate);
			bool hasSideEffect = !Info.CB->hasFnAttr(
					Attribute::AttrKind::Speculatable);
			int opc = HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER;
			if (noDuplicate && hasSideEffect) {
				opc =
						HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT;
			} else if (noDuplicate) {
				opc = HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE;
			} else if (hasSideEffect) {
				opc = HwtFpga::HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT;
			}
			assert(Info.OrigRet.Regs.size() == 1);
			auto DstReg = Info.OrigRet.Regs[0];
			auto MIB = MIRBuilder.buildInstr(opc)	 //
			.addReg(DstReg, RegState::Define);
			MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);

			if (!addIntImmByRegiter(MRI, MIB, Info.OrigArgs[0].Regs[0])) {
				std::string errStr =
						"hwtHls.pyOjbectPlaceholder object id operand must be constant: ";
				llvm::raw_string_ostream ss(errStr);
				Info.CB->print(ss);
				throw std::runtime_error(ss.str());
			}
			uint64_t dstRegWidth = MRI.getType(DstReg).getSizeInBits();
			MIB.addImm(dstRegWidth);

			// add operands
			bool first = true;
			for (auto &op : Info.OrigArgs) {
				if (first) {
					first = false;
					continue;
				}
				MIB.addUse(op.Regs[0]);
			}
			// add input operand widths
			first = true;
			for (auto &op : Info.OrigArgs) {
				if (first) {
					first = false;
					continue; // skip width for objectId input argument
				}
				uint64_t width = MRI.getType(op.Regs[0]).getSizeInBits();
				MIB.addImm(width);
			}
			return true;
		} else if (hwtHls::IsHwtHlsFp(F)) {
			int opc;
			size_t opArgCnt = 2;
			if (hwtHls::IsHwtHlsFpFAdd(F)) {
				opc = HwtFpga::HWTFPGA_FP_FADD;
			} else if (hwtHls::IsHwtHlsFpFSub(F)) {
				opc = HwtFpga::HWTFPGA_FP_FSUB;
			} else if (hwtHls::IsHwtHlsFpFMul(F)) {
				opc = HwtFpga::HWTFPGA_FP_FMUL;
			} else if (hwtHls::IsHwtHlsFpFDiv(F)) {
				opc = HwtFpga::HWTFPGA_FP_FDIV;
			} else {
				std::string errStr = "Not implemented, Unknown hwtHls.fp. intrinsic: ";
				llvm::raw_string_ostream ss(errStr);
				Info.CB->print(ss);
				throw std::runtime_error(ss.str());
			}
			assert(Info.OrigRet.Regs.size() == 1);
			// dst, srcN*, HFloatTmpConfig options as imms
			auto DstReg = Info.OrigRet.Regs[0];
			auto MIB = MIRBuilder.buildInstr(opc)	 //
			.addReg(DstReg, RegState::Define);
			MRI.setRegClass(DstReg, &HwtFpga::anyregclsRegClass);

			assert(Info.OrigArgs.size() == opArgCnt + hwtHls::HFloatTmpConfig::MEMBER_CNT);
			for (size_t i = 0; i < opArgCnt; ++i) {
				MIB.addUse(Info.OrigArgs[i].Regs[0]);
			}

	    	for (size_t i = opArgCnt; i < opArgCnt + hwtHls::HFloatTmpConfig::MEMBER_CNT; ++i) {
				Register cfgRegV = Info.OrigArgs[i].Regs[0];
				if (!addIntImmByRegiter(MRI, MIB, cfgRegV)) {
					std::string errStr =
							"hwtHls.fp.* specialization values must be constants: ";
					llvm::raw_string_ostream ss(errStr);
					Info.CB->print(ss);
					throw std::runtime_error(ss.str());
				}
			}
			return true;
		} else {
			std::string errStr =
					"Not implemented, call of generic function in HW function: ";
			llvm::raw_string_ostream ss(errStr);
			Info.CB->print(ss);
			throw std::runtime_error(ss.str());
		}
	}
	std::string errStr = "Not implemented, lowerCall: ";
	llvm::raw_string_ostream ss(errStr);
	Info.CB->print(ss);
	throw std::runtime_error(ss.str());
}

bool HwtFpgaCallLowering::canLowerReturn(MachineFunction &MF,
		CallingConv::ID CallConv, SmallVectorImpl<BaseArgInfo> &Outs,
		bool IsVarArg) const {
	//assert(Outs.size() == 0 && "HwtFpgaCallLowering::canLowerReturn should be used only for HW functions which do have only void return type.");
	return true;
}

}
