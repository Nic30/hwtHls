#pragma once

#include <llvm/CodeGen/TargetLowering.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetSubtarget.h>

namespace llvm {
class HwtFpgaTargetSubtarget;

class HwtFpgaTargetLowering: public llvm::TargetLowering {
protected:
	const llvm::HwtFpgaTargetSubtarget &Subtarget;

public:
	HwtFpgaTargetLowering(const HwtFpgaTargetLowering&) = delete;
	HwtFpgaTargetLowering& operator=(const HwtFpgaTargetLowering&) = delete;
	explicit HwtFpgaTargetLowering(const llvm::TargetMachine &TM,
			const llvm::HwtFpgaTargetSubtarget &STI);

	virtual bool isSuitableForJumpTable(const SwitchInst *SI, uint64_t NumCases,
			uint64_t Range, ProfileSummaryInfo *PSI,
			BlockFrequencyInfo *BFI) const override {
		return false;
	}
	//virtual MVT getPreferredSwitchConditionType(LLVMContext &Context,
	//		EVT ConditionVT) const override;
	virtual bool canCombineTruncStore(EVT ValVT, EVT MemVT,
			bool LegalOnly) const override {
		return false;
	}
	virtual bool shouldReduceLoadWidth(SDNode *Load, ISD::LoadExtType ExtTy,
			EVT NewVT) const override {
		return false;
	}
	virtual bool allowsMisalignedMemoryAccesses(EVT, unsigned AddrSpace = 0,
			Align Alignment = Align(1), MachineMemOperand::Flags Flags =
					MachineMemOperand::MONone,
			unsigned* /*Fast*/= nullptr) const override {
		return true;
	}
	virtual bool allowsMisalignedMemoryAccesses(LLT, unsigned AddrSpace = 0,
			Align Alignment = Align(1), MachineMemOperand::Flags Flags =
					MachineMemOperand::MONone,
			unsigned* /*Fast*/= nullptr) const override {
		return true;
	}

	virtual bool allowsMemoryAccess(LLVMContext &Context, const DataLayout &DL,
			EVT VT, unsigned AddrSpace = 0, Align Alignment = Align(1),
			MachineMemOperand::Flags Flags = MachineMemOperand::MONone,
			unsigned *Fast = nullptr) const override {
		return true;
	}
	virtual bool getAddrModeArguments(IntrinsicInst* /*I*/,
			SmallVectorImpl<Value*>&/*Ops*/, Type*&/*AccessTy*/) const
					override {
		return true;
	}
	virtual bool isLegalStoreImmediate(int64_t Value) const override {
		return true;
	}
	virtual bool isTruncateFree(Type *FromTy, Type *ToTy) const override {
		return true;
	}

	virtual bool isTruncateFree(EVT FromVT, EVT ToVT) const override {
		return true;
	}
	virtual bool isZExtFree(Type *FromTy, Type *ToTy) const override {
		return true;
	}
	virtual bool isZExtFree(EVT FromTy, EVT ToTy) const override {
		return true;
	}
	virtual bool isNarrowingProfitable(EVT /*VT1*/, EVT /*VT2*/) const
			override {
		return true;
	}
	/// Return the register class that should be used for the specified value
	/// type.
	virtual const llvm::TargetRegisterClass* getRegClassFor(llvm::MVT VT,
			bool isDivergent = false) const override;

	virtual unsigned getNumRegisters(llvm::LLVMContext &Context, llvm::EVT VT,
			std::optional<llvm::MVT> RegisterVT = std::nullopt) const override;
	/// Return the register type for a given MVT, ensuring vectors are treated
	/// as a series of gpr sized integers.
	virtual llvm::MVT getRegisterTypeForCallingConv(llvm::LLVMContext &Context,
			llvm::CallingConv::ID CC, llvm::EVT VT) const override;
	virtual EVT getTypeForExtReturn(LLVMContext &Context, EVT VT,
			ISD::NodeType ExtendKind) const override {
		return VT;
	}
	/// Return the number of registers for a given MVT, ensuring vectors are
	/// treated as a series of gpr sized integers.
	virtual unsigned getNumRegistersForCallingConv(llvm::LLVMContext &Context,
			llvm::CallingConv::ID CC, llvm::EVT VT) const override;

	virtual llvm::SDValue LowerFormalArguments(llvm::SDValue Chain,
			llvm::CallingConv::ID CallConv, bool isVarArg,
			const llvm::SmallVectorImpl<llvm::ISD::InputArg> &Ins,
			const llvm::SDLoc &dl, llvm::SelectionDAG &DAG,
			llvm::SmallVectorImpl<llvm::SDValue> &InVals) const override;
};

}
