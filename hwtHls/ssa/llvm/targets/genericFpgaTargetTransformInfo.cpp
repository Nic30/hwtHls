//===----------------------------------------------------------------------===//
/// \file
/// This file implements a TargetTransformInfo analysis pass specific to the
/// GenericFpga target machine. It uses the target's detailed information to provide
/// more precise answers to certain TTI queries, while letting the target
/// independent and default TTI implementations handle the rest.
///
//===----------------------------------------------------------------------===//

#include "genericFpgaTargetTransformInfo.h"
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/CodeGen/BasicTTIImpl.h>
#include <llvm/CodeGen/CostTable.h>
#include <llvm/CodeGen/TargetLowering.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/KnownBits.h>
#include <llvm/Support/MathExtras.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>

using namespace llvm;

#define DEBUG_TYPE "fpgatti"

//===----------------------------------------------------------------------===//
//
// GenericFpga spmd/simt execution.
//
//===----------------------------------------------------------------------===//

bool GenericFpgaTTIImpl::hasBranchDivergence() {
	return true;
}

static bool IsKernelFunction(const Function &F) {
	return F.getCallingConv() == CallingConv::SPIR_KERNEL;
}

static bool isPureFunction(const IntrinsicInst *II) {
	switch (II->getIntrinsicID()) {
	default:
		return false;
	case Intrinsic::ssa_copy:
		return true;
	}
}

bool GenericFpgaTTIImpl::isSourceOfDivergence(const Value *V) {
	// Without inter-procedural analysis, we conservatively assume that arguments
	// to spir_func functions are divergent.
	if (const Argument *Arg = dyn_cast<Argument>(V))
		return !IsKernelFunction(*Arg->getParent());

	if (const Instruction *I = dyn_cast<Instruction>(V)) {
		// Without pointer analysis, we conservatively assume values loaded from
		// private address space are divergent.
		if (const LoadInst *LI = dyn_cast<LoadInst>(I)) {
			unsigned AS = LI->getPointerAddressSpace();
			return AS == 0;
		}

		// Alloca in private address space are divergent.
		if (const AllocaInst *AI = dyn_cast<AllocaInst>(I)) {
			unsigned AS = AI->getType()->getPointerAddressSpace();
			return AS == 0;
		}

		// Atomic instructions may cause divergence.
		// In CUDA, Atomic instructions are executed sequentially across all threads
		// in a warp. Therefore, an earlier executed thread may see different memory
		// inputs than a later executed thread. For example, suppose *a = 0
		// initially.
		//
		//   atom.global.add.s32 d, [a], 1
		//
		// returns 0 for the first thread that enters the critical region, and 1 for
		// the second thread.
		// TODO: Are there atomic instructions in OpenCL?
		if (I->isAtomic())
			return true;

		if (const IntrinsicInst *II = dyn_cast<IntrinsicInst>(I)) {
			if (isPureFunction(II))
				return false;
		}

		// Conservatively consider the return value of function calls as divergent.
		// We could analyze callees with bodies more precisely using
		// inter-procedural analysis.
		if (isa<CallInst>(I))
			return true;
	}

	return false;
}

//===----------------------------------------------------------------------===//
//
// GenericFpga cost model.
//
//===----------------------------------------------------------------------===//

unsigned GenericFpgaTTIImpl::getIntImmCostInst(unsigned Opcode, unsigned Idx,
		const APInt &Imm, Type *Ty, TTI::TargetCostKind CostKind,
		Instruction *Inst) const {
	switch (Opcode) {
	// Bit functions are free
	case Instruction::BitCast:
	case Instruction::IntToPtr:
	case Instruction::PtrToInt:
	case Instruction::Trunc:
		return TTI::TCC_Free;
	default:
		return BaseT::getIntImmCostInst(Opcode, Idx, Imm, Ty, CostKind, Inst);
	}
}

// Any immediate value can be synthesized
bool GenericFpgaTTIImpl::isLegalAddImmediate(int64_t Imm) {
	return true;
}
bool GenericFpgaTTIImpl::isLegalICmpImmediate(int64_t Imm) {
	return true;
}

// Masked memory operations are free
bool GenericFpgaTTIImpl::isLegalMaskedStore(Type *DataType, Align Alignment) {
	return true;
}
bool GenericFpgaTTIImpl::isLegalMaskedLoad(Type *DataType, Align Alignment) {
	return true;
}

bool GenericFpgaTTIImpl::isTruncateFree(Type *Ty1, Type *Ty2) {
	if (!Ty1->isIntegerTy() || !Ty2->isIntegerTy())
		return false;
	unsigned NumBits1 = Ty1->getPrimitiveSizeInBits();
	unsigned NumBits2 = Ty2->getPrimitiveSizeInBits();
	return NumBits1 > NumBits2;
}

bool GenericFpgaTTIImpl::isTypeLegal(Type *Ty) {
	return true;
}

// Switch as lookup tables is not desired
bool GenericFpgaTTIImpl::shouldBuildLookupTables() {
	return false;
}

TargetTransformInfo::PopcntSupportKind GenericFpgaTTIImpl::getPopcntSupport(
		unsigned IntTyWidthInBit) {
	return TTI::PSK_FastHardware;
}

unsigned GenericFpgaTTIImpl::getNumberOfRegisters(unsigned ClassID) const {
	return std::numeric_limits<unsigned>::max() >> 2;
}

unsigned GenericFpgaTTIImpl::getRegisterBitWidth(bool Vector) const {
	return std::numeric_limits<unsigned>::max() >> 2;
}

unsigned GenericFpgaTTIImpl::getShuffleCost(TTI::ShuffleKind Kind, VectorType *Ty, int Index,
        VectorType *SubTp) const {
	return TTI::TCC_Free;
}

unsigned GenericFpgaTTIImpl::getCastInstrCost(unsigned Opcode, Type *Dst,
		Type *Src, TTI::CastContextHint CCH, TTI::TargetCostKind CostKind,
		const Instruction *I) const {
	return TTI::TCC_Free;
}

unsigned GenericFpgaTTIImpl::getExtractWithExtendCost(unsigned Opcode,
		Type *Dst, VectorType *VecTy, unsigned Index) {
	return TTI::TCC_Free;
}

unsigned GenericFpgaTTIImpl::getVectorInstrCost(unsigned Opcode, Type *Val,
		unsigned Index) {
	return TTI::TCC_Free;
}

static bool IsBitwiseBinaryOperator(unsigned Opcode) {
	switch (Opcode) {
	default:
		return Instruction::isShift(Opcode);
	case Instruction::And:
	case Instruction::Or:
	case Instruction::Xor:
	case Instruction::ExtractElement:
	case Instruction::ExtractValue:
	case Instruction::InsertElement:
	case Instruction::InsertValue:
		return true;
	}
}

static bool IsFreeOperator(const User *U) {
	if (isa<BitCastOperator>(U))
		return true;

	auto *O = dyn_cast<Operator>(U);
	if (!O)
		return false;

	auto Opcode = O->getOpcode();

	// Bitwise operator with constant on RHS is definitely free.
	// Notice that a free bitwise operator is not necessary having a constant RHS
	Value *RHS = *std::prev(U->op_end());
	if (IsBitwiseBinaryOperator(Opcode) && isa<Constant>(RHS))
		return true;

	return false;
}

unsigned GenericFpgaTTIImpl::getUserCost(const User *U,
		ArrayRef<const Value*> Operands, TTI::TargetCostKind CostKind) {
	if (IsFreeOperator(U))
		return TTI::TCC_Free;

	return BaseT::getUserCost(U, Operands, CostKind);
}

void GenericFpgaTTIImpl::getUnrollingPreferences(Loop *L, ScalarEvolution &SE,
		TTI::UnrollingPreferences &UP) {
	UP.Threshold = 0;
	UP.PartialThreshold = 0;
	UP.Count = 1;
	UP.MaxCount = 1;
	UP.FullUnrollMaxCount = 1;
	UP.Partial = false;
	UP.Runtime = false;
	UP.AllowRemainder = false;
}

Type* GenericFpgaTTIImpl::getMemcpyLoopLoweringType(LLVMContext &Context,
		Value *Length, unsigned SrcAddrSpace, unsigned DestAddrSpace,
		unsigned SrcAlign, unsigned DestAlign) const {
	uint64_t Min = MinAlign(SrcAlign, DestAlign);
	KnownBits KB = computeKnownBits(Length, getDataLayout());
	Min = MinAlign(Min, 1 << KB.countMinTrailingZeros());
	return IntegerType::get(Context, 8 * Min);
}

unsigned GenericFpgaTTIImpl::getLoadStoreVecRegBitWidth(
		unsigned AddrSpace) const {
	return 512;
}

bool GenericFpgaTTIImpl::isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes,
		Align Alignment, unsigned AddrSpace) const {
	return true;
}

bool GenericFpgaTTIImpl::isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
		Align Alignment, unsigned AddrSpace) const {
	return true;
}
