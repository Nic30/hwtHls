#include <hwtHls/llvm/targets/GISel/hwtFpgaLegalizerInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetSubtarget.h>
#include <hwtHls/llvm/targets/bitMathUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>

#include <llvm/CodeGen/GlobalISel/LegalizerHelper.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>


#ifdef LLVM_NDEBUG
#define NDEBUG 1
#endif

namespace llvm {

HwtFpgaLegalizerInfo::HwtFpgaLegalizerInfo(const HwtFpgaTargetSubtarget &ST) :
		LegalizerInfo(), TII(*ST.getInstrInfo()) {
	//auto & LLI = getLegacyLegalizerInfo();
	using namespace TargetOpcode;
	// add natively supported ops as legal
	for (auto op : { G_IMPLICIT_DEF, G_CONSTANT, G_GLOBAL_VALUE, G_SELECT,
			G_BRCOND, G_ICMP, G_ADD, G_SUB, G_MUL, G_UREM, G_UDIV, G_SREM,
			G_SDIV, G_LOAD, G_STORE, G_INDEXED_LOAD, G_INDEXED_STORE, G_PHI,
			G_AND, G_OR, G_XOR, G_EXTRACT, G_MERGE_VALUES, G_ZEXT, G_SEXT,
			G_PTR_ADD,
	}) {
		getActionDefinitionsBuilder(op) //
		.alwaysLegal();
	}
	getActionDefinitionsBuilder( {
		G_SEXTLOAD, G_ZEXTLOAD,
		// shift and bit ops
		G_SHL, G_LSHR, G_ASHR,
		G_CTLZ_ZERO_UNDEF, G_CTTZ_ZERO_UNDEF,
		G_CTLZ, G_CTTZ, G_CTPOP,
		// see llvm::FreezeInst
		G_FREEZE,
	}).custom();
	//.lower();
	getActionDefinitionsBuilder( {
		// high order functions
		G_MEMCPY, G_MEMCPY_INLINE, G_MEMMOVE,
	    G_MEMSET, G_ABS, G_SMIN, G_SMAX, G_UMAX, G_UMIN,
		// funnel shifts/rotations
		G_FSHL, G_FSHR,
	    G_SEXT_INREG,
	    // saturated arithmetic
	    G_SADDSAT, G_UADDSAT, G_SSUBSAT, G_USUBSAT, G_SSHLSAT, G_USHLSAT,
	    // add/sub/modulo with carry out
	    G_UADDO, G_SADDO, G_USUBO, G_SSUBO, G_SMULO, G_UMULO,
	}).lower();

	//getActionDefinitionsBuilder({G_VASTART, G_VAARG, G_BRJT, G_JUMP_TABLE,
	//      G_INDEXED_LOAD, G_INDEXED_SEXTLOAD,
	//      G_INDEXED_ZEXTLOAD, G_INDEXED_STORE})
	//  .unsupported();

	//LLI.computeTables();
	getLegacyLegalizerInfo().computeTables();
	verify(*ST.getInstrInfo());
}

bool HwtFpgaLegalizerInfo::customLowerLoad(LegalizerHelper &Helper,
		GAnyLoad &LoadMI) const {
	// :note: taken from LegalizerHelper::lowerLoad because it does not work for G_SEXTLOAD of aligned types
	MachineFunction &MF = Helper.MIRBuilder.getMF();
	MachineIRBuilder &MIRBuilder = Helper.MIRBuilder;
	MachineRegisterInfo &MRI = MF.getRegInfo();
	const TargetLowering &TLI = *MF.getSubtarget().getTargetLowering();

	Register DstReg = LoadMI.getDstReg();
	Register PtrReg = LoadMI.getPointerReg();

	LLT DstTy = MRI.getType(DstReg);
	MachineMemOperand &MMO = LoadMI.getMMO();
	LLT MemTy = MMO.getMemoryType();

	unsigned MemSizeInBits = MemTy.getSizeInBits();
	unsigned MemStoreSizeInBits = 8 * MemTy.getSizeInBytes();
	auto &Ctx = MF.getFunction().getContext();
	if (MemSizeInBits != MemStoreSizeInBits
			|| TLI.allowsMemoryAccess(Ctx, MIRBuilder.getDataLayout(), MemTy,
					MMO)) {
		if (MemTy.isVector())
			return false;

		// Promote to a byte-sized load if not loading an integral number of
		// bytes.  For example, promote EXTLOAD:i20 -> EXTLOAD:i24.
		LLT WideMemTy = LLT::scalar(MemStoreSizeInBits);
		MachineMemOperand *NewMMO = MF.getMachineMemOperand(&MMO,
				MMO.getPointerInfo(), WideMemTy);

		Register LoadReg = DstReg;
		LLT LoadTy = DstTy;

		// If this wasn't already an extending load, we need to widen the result
		// register to avoid creating a load with a narrower result than the source.
		if (MemStoreSizeInBits > DstTy.getSizeInBits()) {
			LoadTy = WideMemTy;
			LoadReg = MRI.createGenericVirtualRegister(WideMemTy);
		}

		if (isa<GSExtLoad>(LoadMI)) {
			auto NewLoad = MIRBuilder.buildLoad(LoadTy, PtrReg, *NewMMO);
			MIRBuilder.buildSExtInReg(LoadReg, NewLoad, MemSizeInBits);
		} else if (isa<GZExtLoad>(LoadMI) || WideMemTy == DstTy) {
			auto NewLoad = MIRBuilder.buildLoad(LoadTy, PtrReg, *NewMMO);
			// The extra bits are guaranteed to be zero, since we stored them that
			// way.  A zext load from Wide thus automatically gives zext from MemVT.
			MIRBuilder.buildAssertZExt(LoadReg, NewLoad, MemSizeInBits);
		} else {
			MIRBuilder.buildLoad(LoadReg, PtrReg, *NewMMO);
		}

		if (DstTy != LoadTy)
			MIRBuilder.buildTrunc(DstReg, LoadReg);

		LoadMI.eraseFromParent();
		return true;
	}
	return false;
}

bool HwtFpgaLegalizerInfo::legalizeCustomBitcount(LegalizerHelper &Helper,
		MachineInstr &MI) const {
	MachineFunction &MF = Helper.MIRBuilder.getMF();
	MachineIRBuilder &MIRBuilder = Helper.MIRBuilder;
	MachineRegisterInfo &MRI = MF.getRegInfo();

	Register Dst = MI.getOperand(0).getReg();
	const auto & SrcMO = MI.getOperand(1);
	Register Src = SrcMO.getReg();
	LLT DstTy = MRI.getType(Dst);
	LLT SrcTy = MRI.getType(Src);
	unsigned dataWidth = SrcTy.getSizeInBits();
	assert(dataWidth == DstTy.getSizeInBits());
	unsigned NewOpc;
	switch (MI.getOpcode()) {
	case TargetOpcode::G_CTLZ_ZERO_UNDEF:
		NewOpc = HwtFpga::HWTFPGA_CTLZ_ZERO_UNDEF;
		break;
	case TargetOpcode::G_CTTZ_ZERO_UNDEF:
		NewOpc = HwtFpga::HWTFPGA_CTTZ_ZERO_UNDEF;
		break;
	case TargetOpcode::G_CTLZ:
		NewOpc = HwtFpga::HWTFPGA_CTLZ;
		break;
	case TargetOpcode::G_CTTZ:
		NewOpc = HwtFpga::HWTFPGA_CTTZ;
		break;
	case TargetOpcode::G_CTPOP:
		NewOpc = HwtFpga::HWTFPGA_CTPOP;
		break;
	default:
		errs() << MI << "\n";
		llvm_unreachable("NotImplemented bit count");
	}

	unsigned newBitWidth = log2ceil(dataWidth + 1);
	auto DstTruncated = MRI.cloneVirtualRegister(Dst);
	MIRBuilder.buildInstr(NewOpc, { DstTruncated }, { Src });
	MRI.setType(DstTruncated, LLT::scalar(newBitWidth));

	for (auto R : { DstTruncated, Src })
		MRI.setRegClass(R, &HwtFpga::anyregclsRegClass);

	auto MIB1 = MIRBuilder.buildInstr(NewOpc, { Dst }, { });
	auto DstTruncatedMO = MachineOperand::CreateReg(DstTruncated, false);
	hwtHls::HwtFpgaInstructionSelector::selectInstrArg(MF, MIB1, MRI, DstTruncatedMO);

	MIRBuilder.buildZExt(Dst, DstTruncated);

	MI.eraseFromParent();
	return true;
}

bool HwtFpgaLegalizerInfo::legalizeCustomShift(LegalizerHelper &Helper,
		MachineInstr &MI) const {
	MachineFunction &MF = Helper.MIRBuilder.getMF();
	MachineIRBuilder &MIRBuilder = Helper.MIRBuilder;
	MachineRegisterInfo &MRI = MF.getRegInfo();

	Register Dst = MI.getOperand(0).getReg();
	auto &SrcMO = MI.getOperand(1);
	Register Src = SrcMO.getReg();
	Register Sh = MI.getOperand(2).getReg();
	LLT DstTy = MRI.getType(Dst);
	LLT SrcTy = MRI.getType(Src);
	LLT ShTy = MRI.getType(Sh);
	unsigned dataWidth = SrcTy.getSizeInBits();
	assert(dataWidth == DstTy.getSizeInBits());
	assert(dataWidth == ShTy.getSizeInBits());

	unsigned newShBitWidth = log2ceil(dataWidth + 1);

	unsigned NewOpc;
	switch (MI.getOpcode()) {
	case TargetOpcode::G_SHL:
		NewOpc = HwtFpga::HWTFPGA_SHL;
		break;
	case TargetOpcode::G_LSHR:
		NewOpc = HwtFpga::HWTFPGA_LSHR;
		break;
	case TargetOpcode::G_ASHR:
		NewOpc = HwtFpga::HWTFPGA_ASHR;
		break;
	default:
		errs() << MI << "\n";
		llvm_unreachable("NotImplemented shift");
	}

	auto ShTruncated = MRI.cloneVirtualRegister(Sh);
	MRI.setType(ShTruncated, LLT::scalar(newShBitWidth));
	MIRBuilder.buildTrunc(ShTruncated, Sh);
	auto ShTruncatedMO = MachineOperand::CreateReg(ShTruncated, false);

	auto MIB1 = MIRBuilder.buildInstr(NewOpc, { Dst }, { });
	for (auto R : { Dst, Src, ShTruncated })
		MRI.setRegClass(R, &HwtFpga::anyregclsRegClass);

	hwtHls::HwtFpgaInstructionSelector::selectInstrArg(MF, MIB1, MRI, SrcMO);
	hwtHls::HwtFpgaInstructionSelector::selectInstrArg(MF, MIB1, MRI,
			ShTruncatedMO);

	MI.eraseFromParent();
	return true;
}


bool HwtFpgaLegalizerInfo::legalizeCustom(LegalizerHelper &Helper,
		MachineInstr &MI) const {

	switch (MI.getOpcode()) {
	case TargetOpcode::G_SHL:
	case TargetOpcode::G_LSHR:
	case TargetOpcode::G_ASHR: {
		if (legalizeCustomShift(Helper, MI))
			return true;
		break;
	}
	case TargetOpcode::G_CTLZ_ZERO_UNDEF:
	case TargetOpcode::G_CTTZ_ZERO_UNDEF:
	case TargetOpcode::G_CTLZ:
	case TargetOpcode::G_CTTZ:
	case TargetOpcode::G_CTPOP: {
		if (legalizeCustomBitcount(Helper, MI))
			return true;
		break;
	}
	case TargetOpcode::G_FREEZE: {
		MachineFunction &MF = Helper.MIRBuilder.getMF();
		MachineRegisterInfo &MRI = MF.getRegInfo();
		MI.setDesc(TII.get(TargetOpcode::COPY));
		MRI.setRegClass(MI.getOperand(0).getReg(), &HwtFpga::anyregclsRegClass);
		return true;
	}
	case TargetOpcode::G_ZEXTLOAD:
	case TargetOpcode::G_SEXTLOAD:
		if (customLowerLoad(Helper, cast<GAnyLoad>(MI)))
			return true;
		return Helper.lowerLoad(cast<GAnyLoad>(MI))
				!= LegalizerHelper::LegalizeResult::UnableToLegalize;
	}
	return Helper.lower(MI, 0, LLT()) != LegalizerHelper::LegalizeResult::UnableToLegalize;
}

}
