#pragma once

#include <llvm/CodeGen/TargetLowering.h>
#include "genericFpgaTargetSubtarget.h"

namespace llvm {
class GenericFpgaTargetSubtarget;

class GenericFpgaTargetLowering: public llvm::TargetLowering {
protected:
	const llvm::GenericFpgaTargetSubtarget &Subtarget;

public:
	GenericFpgaTargetLowering(const GenericFpgaTargetLowering&) = delete;
	GenericFpgaTargetLowering& operator=(const GenericFpgaTargetLowering&) = delete;
	explicit GenericFpgaTargetLowering(const llvm::TargetMachine &TM,
			const llvm::GenericFpgaTargetSubtarget &STI);


	bool isSuitableForJumpTable(const SwitchInst *SI, uint64_t NumCases,
			uint64_t Range, ProfileSummaryInfo *PSI,
			BlockFrequencyInfo *BFI) const override {
		return false;
	}

	bool canCombineTruncStore(EVT ValVT, EVT MemVT, bool LegalOnly) const
			override {
		return false;
	}
	bool shouldReduceLoadWidth(SDNode *Load, ISD::LoadExtType ExtTy,
			EVT NewVT) const override {
		return false;
	}
	bool allowsMisalignedMemoryAccesses(EVT, unsigned AddrSpace = 0,
			Align Alignment = Align(1), MachineMemOperand::Flags Flags =
					MachineMemOperand::MONone, bool* /*Fast*/= nullptr) const
					override {
		return true;
	}
	bool allowsMisalignedMemoryAccesses(LLT, unsigned AddrSpace = 0,
			Align Alignment = Align(1), MachineMemOperand::Flags Flags =
					MachineMemOperand::MONone, bool* /*Fast*/= nullptr) const
					override {
		return true;
	}
	bool allowsMemoryAccess(LLVMContext &Context, const DataLayout &DL, EVT VT,
			unsigned AddrSpace = 0, Align Alignment = Align(1),
			MachineMemOperand::Flags Flags = MachineMemOperand::MONone,
			bool *Fast = nullptr) const override {
		return true;
	}
	bool getAddrModeArguments(IntrinsicInst* /*I*/,
			SmallVectorImpl<Value*>&/*Ops*/, Type*&/*AccessTy*/) const
					override {
		return true;
	}
	bool isLegalStoreImmediate(int64_t Value) const override {
		return true;
	}
	bool isTruncateFree(Type *FromTy, Type *ToTy) const override {
		return true;
	}

	bool isTruncateFree(EVT FromVT, EVT ToVT) const override {
		return true;
	}
	bool isZExtFree(Type *FromTy, Type *ToTy) const override {
		return true;
	}
	bool isZExtFree(EVT FromTy, EVT ToTy) const override {
		return true;
	}
	bool isNarrowingProfitable(EVT /*VT1*/, EVT /*VT2*/) const override {
		return true;
	}
	/// Return the register class that should be used for the specified value
	/// type.
	const llvm::TargetRegisterClass* getRegClassFor(llvm::MVT VT,
			bool isDivergent = false) const override;

	unsigned getNumRegisters(llvm::LLVMContext &Context, llvm::EVT VT,
			llvm::Optional<llvm::MVT> RegisterVT = llvm::None) const override;
	/// Return the register type for a given MVT, ensuring vectors are treated
	/// as a series of gpr sized integers.
	llvm::MVT getRegisterTypeForCallingConv(llvm::LLVMContext &Context,
			llvm::CallingConv::ID CC, llvm::EVT VT) const override;
	EVT getTypeForExtReturn(LLVMContext &Context, EVT VT,
			ISD::NodeType ExtendKind) const override {
		return VT;
	}
	/// Return the number of registers for a given MVT, ensuring vectors are
	/// treated as a series of gpr sized integers.
	unsigned getNumRegistersForCallingConv(llvm::LLVMContext &Context,
			llvm::CallingConv::ID CC, llvm::EVT VT) const override;

	llvm::SDValue LowerFormalArguments(llvm::SDValue Chain,
			llvm::CallingConv::ID CallConv, bool isVarArg,
			const llvm::SmallVectorImpl<llvm::ISD::InputArg> &Ins,
			const llvm::SDLoc &dl, llvm::SelectionDAG &DAG,
			llvm::SmallVectorImpl<llvm::SDValue> &InVals) const override;

};

}