#pragma once

#include "hwtFpgaTargetMachine.h"
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
			BaseT(F.getParent()->getDataLayout()), TM(TM), ST(
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
			llvm::Instruction *Inst = nullptr) const;
	llvm::InstructionCost getInstructionCost(const llvm::User *U,
			llvm::ArrayRef<const llvm::Value*> Operands, TTI::TargetCostKind CostKind);
	unsigned getNumberOfRegisters(unsigned ClassID) const;
	bool hasBranchDivergence();
	bool isSourceOfDivergence(const llvm::Value *V);
	void getUnrollingPreferences(llvm::Loop *, llvm::ScalarEvolution &,
	                               llvm::TTI::UnrollingPreferences &,
	                               llvm::OptimizationRemarkEmitter *) const;
	bool isLegalAddImmediate(int64_t Imm) const;
	bool isLegalICmpImmediate(int64_t Imm) const;
	bool isLegalMaskedStore(llvm::Type *DataType, llvm::Align Alignment) const;
	bool isLegalMaskedLoad(llvm::Type *DataType, llvm::Align Alignment) const;
	bool isTruncateFree(llvm::Type *Ty1, llvm::Type *Ty2) const;
	bool isTypeLegal(llvm::Type *Ty) const;
	bool shouldBuildLookupTables() const;
	bool shouldBuildLookupTablesForConstant(Constant *C) const;
	TTI::PopcntSupportKind getPopcntSupport(unsigned IntTyWidthInBit);
	llvm::TypeSize getRegisterBitWidth(bool Vector) const;

	llvm::InstructionCost getShuffleCost(TTI::ShuffleKind Kind, llvm::VectorType *Ty, llvm::ArrayRef<int> Mask,
            TTI::TargetCostKind CostKind, int Index, llvm::VectorType *SubTp,
            llvm::ArrayRef<const llvm::Value *> Args = std::nullopt) const;
	llvm::InstructionCost getCastInstrCost(unsigned Opcode, llvm::Type *Dst,
			llvm::Type *Src, TTI::CastContextHint CCH,
			TTI::TargetCostKind CostKind, const llvm::Instruction *I) const;
	llvm::InstructionCost getExtractWithExtendCost(unsigned Opcode,
			llvm::Type *Dst, llvm::VectorType *VecTy, unsigned Index) const;
	llvm::InstructionCost getVectorInstrCost(unsigned Opcode, Type *Val,
			TTI::TargetCostKind CostKind, unsigned Index, llvm::Value *Op0,
			llvm::Value *Op1) const;
	llvm::InstructionCost getVectorInstrCost(const Instruction &I, Type *Val,
			TTI::TargetCostKind CostKind, unsigned Index) const;
	llvm::Type* getMemcpyLoopLoweringType(llvm::LLVMContext &Context,
			llvm::Value *Length, unsigned SrcAddrSpace, unsigned DestAddrSpace,
			unsigned SrcAlign, unsigned DestAlign, std::optional<uint32_t> AtomicElementSize) const;
	unsigned getLoadStoreVecRegBitWidth(unsigned AddrSpace) const;
	bool isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const;
	bool isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const;
};

}
