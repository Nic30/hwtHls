#pragma once

#include "genericFpgaTargetMachine.h"
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/TargetTransformInfoImpl.h>

namespace llvm {

/**
 * Container of informations about the target.
 * */
class GenericFpgaTTIImpl final: public TargetTransformInfoImplCRTPBase<
		GenericFpgaTTIImpl> {
protected:
	typedef TargetTransformInfoImplCRTPBase<GenericFpgaTTIImpl> BaseT;
	friend BaseT;

	const GenericFpgaTargetMachine *TM;
	const GenericFpgaSubtarget *ST;

	const GenericFpgaTargetMachine* getTM() const {
		return TM;
	}
	const GenericFpgaSubtarget* getST() const {
		return ST;
	}

public:
	typedef TargetTransformInfo TTI;

	explicit GenericFpgaTTIImpl(const GenericFpgaTargetMachine *TM,
			const Function &F) :
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

	unsigned getIntImmCostInst(unsigned Opcode, unsigned Idx, const APInt &Imm,
			Type *Ty, TTI::TargetCostKind CostKind,
			Instruction *Inst = nullptr) const;
	unsigned getUserCost(const User *U, ArrayRef<const Value*> Operands,
			TTI::TargetCostKind CostKind);

	unsigned getNumberOfRegisters(unsigned ClassID) const;
	bool hasBranchDivergence();
	bool isSourceOfDivergence(const Value *V);
	void getUnrollingPreferences(Loop *L, ScalarEvolution &SE,
			TTI::UnrollingPreferences &UP);
	bool isLegalAddImmediate(int64_t Imm);
	bool isLegalICmpImmediate(int64_t Imm);
	bool isLegalMaskedStore(Type *DataType, Align Alignment);
	bool isLegalMaskedLoad(Type *DataType, Align Alignment);
	bool isTruncateFree(Type *Ty1, Type *Ty2);
	bool isTypeLegal(Type *Ty);
	bool shouldBuildLookupTables();
	TTI::PopcntSupportKind getPopcntSupport(unsigned IntTyWidthInBit);
	unsigned getRegisterBitWidth(bool Vector) const;
	unsigned getShuffleCost(TTI::ShuffleKind Kind, VectorType *Ty, int Index,
			VectorType *SubTp) const;
	unsigned getCastInstrCost(unsigned Opcode, Type *Dst, Type *Src,
			TTI::CastContextHint CCH, TTI::TargetCostKind CostKind,
			const Instruction *I) const;
	unsigned getExtractWithExtendCost(unsigned Opcode, Type *Dst,
			VectorType *VecTy, unsigned Index);
	unsigned getVectorInstrCost(unsigned Opcode, Type *Val, unsigned Index);
	Type* getMemcpyLoopLoweringType(LLVMContext &Context, Value *Length,
			unsigned SrcAddrSpace, unsigned DestAddrSpace, unsigned SrcAlign,
			unsigned DestAlign) const;

	unsigned getLoadStoreVecRegBitWidth(unsigned AddrSpace) const;
	bool isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes, Align Alignment,
			unsigned AddrSpace) const;
	bool isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
			Align Alignment, unsigned AddrSpace) const;
};

}
