#pragma once

#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/TargetTransformInfoImpl.h>

namespace llvm {

/**
 * Container of informations about the target.
 * */
class HwtFpgaTTIImpl final: public llvm::TargetTransformInfoImplCRTPBase<
		HwtFpgaTTIImpl> {
protected:
	typedef TargetTransformInfoImplCRTPBase<HwtFpgaTTIImpl> BaseT;
	friend BaseT;

	const HwtFpgaTargetMachine *TM;
	const HwtFpgaTargetSubtarget *ST;

	const HwtFpgaTargetMachine* getTM() const {
		return TM;
	}
	const HwtFpgaTargetSubtarget* getST() const {
		return ST;
	}

public:
	typedef llvm::TargetTransformInfo TTI;

	explicit HwtFpgaTTIImpl(const HwtFpgaTargetMachine *TM,
			const llvm::Function &F) :
			BaseT(F.getDataLayout()), TM(TM), ST(
					TM->getSubtargetImpl(F)) {
	}

	// Provide value semantics. MSVC requires that we spell all of these out.
	HwtFpgaTTIImpl(const HwtFpgaTTIImpl &Arg) :
			BaseT(static_cast<const BaseT&>(Arg)), TM(Arg.TM), ST(Arg.ST) {
	}
	HwtFpgaTTIImpl(HwtFpgaTTIImpl &&Arg) :
			BaseT(std::move(static_cast<BaseT&>(Arg))), TM(std::move(Arg.TM)), ST(
					std::move(Arg.ST)) {
	}

	llvm::InstructionCost getIntImmCostInst(unsigned Opcode, unsigned Idx,
			const llvm::APInt &Imm, llvm::Type *Ty,
			TTI::TargetCostKind CostKind,
			llvm::Instruction *Inst = nullptr) const override;
	llvm::InstructionCost getInstructionCost(const llvm::User *U,
			llvm::ArrayRef<const llvm::Value*> Operands, TTI::TargetCostKind CostKind) const override;
	unsigned getNumberOfRegisters(unsigned ClassID) const;
	bool hasBranchDivergence(const Function *F = nullptr) const override;
	bool isSourceOfDivergence(const llvm::Value *V) const override;
	void getUnrollingPreferences(llvm::Loop *, llvm::ScalarEvolution &,
	                               llvm::TTI::UnrollingPreferences &,
	                               llvm::OptimizationRemarkEmitter *) const;
	bool isLegalAddImmediate(int64_t Imm) const override;
	bool isLegalICmpImmediate(int64_t Imm) const override;
	bool isLegalMaskedStore(llvm::Type *DataType, llvm::Align Alignment, unsigned AddressSpace) const override;
	bool isLegalMaskedLoad(llvm::Type *DataType, llvm::Align Alignment, unsigned AddressSpace) const override;
	bool isTruncateFree(llvm::Type *Ty1, llvm::Type *Ty2) const override;
	bool isTypeLegal(llvm::Type *Ty) const override;
	bool shouldBuildLookupTables() const override;
	bool shouldBuildLookupTablesForConstant(Constant *C) const override;
	TTI::PopcntSupportKind getPopcntSupport(unsigned IntTyWidthInBit) const;

	llvm::TypeSize getRegisterBitWidth(TargetTransformInfo::RegisterKind K) const override;

	llvm::InstructionCost getShuffleCost(TTI::ShuffleKind Kind, VectorType *DstTy, VectorType *SrcTy,
            ArrayRef<int> Mask, TTI::TargetCostKind CostKind, int Index,
            VectorType *SubTp, ArrayRef<const Value *> Args = {},
            const Instruction *CxtI = nullptr) const override;
	llvm::InstructionCost getCastInstrCost(unsigned Opcode, llvm::Type *Dst,
			llvm::Type *Src, TTI::CastContextHint CCH,
			TTI::TargetCostKind CostKind, const llvm::Instruction *I) const override;

	llvm::InstructionCost getExtractWithExtendCost(unsigned Opcode,
			llvm::Type *Dst, llvm::VectorType *VecTy, unsigned Index, TTI::TargetCostKind CostKind) const override;
	llvm::InstructionCost getVectorInstrCost(const Instruction &I, Type *Val,
			TTI::TargetCostKind CostKind, unsigned Index) const override;
	llvm::Type* getMemcpyLoopLoweringType(LLVMContext &Context, Value *Length,
            unsigned SrcAddrSpace, unsigned DestAddrSpace,
            Align SrcAlign, Align DestAlign,
            std::optional<uint32_t> AtomicElementSize) const override;
	unsigned getLoadStoreVecRegBitWidth(unsigned AddrSpace) const override;
	bool isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const override;
	bool isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const override;
};

}
