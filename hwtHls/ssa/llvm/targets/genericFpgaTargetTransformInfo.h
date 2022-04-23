#pragma once

#include "genericFpgaTargetMachine.h"
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/TargetTransformInfoImpl.h>

namespace llvm {

/**
 * Container of informations about the target.
 * */
class GenericFpgaTTIImpl final: public llvm::TargetTransformInfoImplCRTPBase<
		GenericFpgaTTIImpl> {
protected:
	typedef TargetTransformInfoImplCRTPBase<GenericFpgaTTIImpl> BaseT;
	friend BaseT;

	const GenericFpgaTargetMachine *TM;
	const GenericFpgaTargetSubtarget *ST;

	const GenericFpgaTargetMachine* getTM() const {
		return TM;
	}
	const GenericFpgaTargetSubtarget* getST() const {
		return ST;
	}

public:
	typedef llvm::TargetTransformInfo TTI;

	explicit GenericFpgaTTIImpl(const GenericFpgaTargetMachine *TM,
			const llvm::Function &F) :
			BaseT(F.getParent()->getDataLayout()), TM(TM), ST(
					TM->getSubtargetImpl(F)) {
	}

	// Provide value semantics. MSVC requires that we spell all of these out.
	GenericFpgaTTIImpl(const GenericFpgaTTIImpl &Arg) :
			BaseT(static_cast<const BaseT&>(Arg)), TM(Arg.TM), ST(Arg.ST) {
	}
	GenericFpgaTTIImpl(GenericFpgaTTIImpl &&Arg) :
			BaseT(std::move(static_cast<BaseT&>(Arg))), TM(std::move(Arg.TM)), ST(
					std::move(Arg.ST)) {
	}

	llvm::InstructionCost getIntImmCostInst(unsigned Opcode, unsigned Idx,
			const llvm::APInt &Imm, llvm::Type *Ty,
			TTI::TargetCostKind CostKind,
			llvm::Instruction *Inst = nullptr) const;
	llvm::InstructionCost getUserCost(const llvm::User *U,
			llvm::ArrayRef<const llvm::Value*> Operands,
			TTI::TargetCostKind CostKind);

	unsigned getNumberOfRegisters(unsigned ClassID) const;
	bool hasBranchDivergence();
	bool isSourceOfDivergence(const llvm::Value *V);
	void getUnrollingPreferences(llvm::Loop *L, llvm::ScalarEvolution &SE,
			TTI::UnrollingPreferences &UP);
	bool isLegalAddImmediate(int64_t Imm);
	bool isLegalICmpImmediate(int64_t Imm);
	bool isLegalMaskedStore(llvm::Type *DataType, llvm::Align Alignment);
	bool isLegalMaskedLoad(llvm::Type *DataType, llvm::Align Alignment);
	bool isTruncateFree(llvm::Type *Ty1, llvm::Type *Ty2);
	bool isTypeLegal(llvm::Type *Ty);
	bool shouldBuildLookupTables();
	TTI::PopcntSupportKind getPopcntSupport(unsigned IntTyWidthInBit);
	llvm::TypeSize getRegisterBitWidth(bool Vector) const;

	llvm::InstructionCost getShuffleCost(TTI::ShuffleKind Kind,
			llvm::VectorType *Ty, llvm::ArrayRef<int> Mask, int Index,
			llvm::VectorType *SubTp) const;
	llvm::InstructionCost getCastInstrCost(unsigned Opcode, llvm::Type *Dst,
			llvm::Type *Src, TTI::CastContextHint CCH,
			TTI::TargetCostKind CostKind, const llvm::Instruction *I) const;
	llvm::InstructionCost getExtractWithExtendCost(unsigned Opcode,
			llvm::Type *Dst, llvm::VectorType *VecTy, unsigned Index);
	llvm::InstructionCost getVectorInstrCost(unsigned Opcode, llvm::Type *Val,
			unsigned Index);
	llvm::Type* getMemcpyLoopLoweringType(llvm::LLVMContext &Context,
			llvm::Value *Length, unsigned SrcAddrSpace, unsigned DestAddrSpace,
			unsigned SrcAlign, unsigned DestAlign) const;

	unsigned getLoadStoreVecRegBitWidth(unsigned AddrSpace) const;
	bool isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const;
	bool isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
			llvm::Align Alignment, unsigned AddrSpace) const;
};

}
