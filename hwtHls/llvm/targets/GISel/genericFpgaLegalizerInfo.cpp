#include "genericFpgaLegalizerInfo.h"
#include "../genericFpgaTargetSubtarget.h"
#include <llvm/CodeGen/GlobalISel/LegalizerHelper.h>

#ifdef LLVM_NDEBUG
#define NDEBUG 1
#endif

namespace llvm {

GenericFpgaLegalizerInfo::GenericFpgaLegalizerInfo(
		const GenericFpgaTargetSubtarget &ST) :
		LegalizerInfo() {
	//auto & LLI = getLegacyLegalizerInfo();
	using namespace TargetOpcode;
	// add natively supported ops as legal
	for (auto op : { G_IMPLICIT_DEF, G_CONSTANT, G_GLOBAL_VALUE, G_SELECT, G_BRCOND, G_ICMP,
			G_ADD, G_SUB, G_MUL, G_LOAD, G_STORE, G_INDEXED_LOAD,
			G_INDEXED_STORE, G_PHI, G_AND, G_OR, G_XOR, G_EXTRACT,
			G_MERGE_VALUES, G_ZEXT, G_SEXT, G_PTR_ADD, G_SHL, G_LSHR, G_ASHR }) {
		getActionDefinitionsBuilder(op) //
		.alwaysLegal();
	}
	getActionDefinitionsBuilder( { G_SEXTLOAD, G_ZEXTLOAD }).custom();
	//.lower();
	getActionDefinitionsBuilder( { G_MEMCPY, G_MEMCPY_INLINE, G_MEMMOVE,
			G_MEMSET }).lower();
	getActionDefinitionsBuilder(G_SEXT_INREG).lower();


	//getActionDefinitionsBuilder({G_VASTART, G_VAARG, G_BRJT, G_JUMP_TABLE,
	//      G_INDEXED_LOAD, G_INDEXED_SEXTLOAD,
	//      G_INDEXED_ZEXTLOAD, G_INDEXED_STORE})
	//  .unsupported();

	//LLI.computeTables();
	getLegacyLegalizerInfo().computeTables();
	verify(*ST.getInstrInfo());
}

bool GenericFpgaLegalizerInfo::customLowerLoad(LegalizerHelper &Helper,
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

bool GenericFpgaLegalizerInfo::legalizeCustom(LegalizerHelper &Helper,
		MachineInstr &MI) const {
	switch (MI.getOpcode()) {
	case TargetOpcode::G_ZEXTLOAD:
	case TargetOpcode::G_SEXTLOAD:
		if (customLowerLoad(Helper, cast<GAnyLoad>(MI)))
			return true;
		return Helper.lowerLoad(cast<GAnyLoad>(MI))
				!= LegalizerHelper::LegalizeResult::UnableToLegalize;
	}
	return false;
}

}
