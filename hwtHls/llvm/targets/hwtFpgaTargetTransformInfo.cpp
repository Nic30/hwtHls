//===----------------------------------------------------------------------===//
/// \file
/// This file implements a TargetTransformInfo analysis pass specific to the
/// HwtFpga target machine. It uses the target's detailed information to provide
/// more precise answers to certain TTI queries, while letting the target
/// independent and default TTI implementations handle the rest.
///
//===----------------------------------------------------------------------===//

#include <hwtHls/llvm/targets/hwtFpgaTargetTransformInfo.h>
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
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

#define DEBUG_TYPE "hwtfpgatti"

//===----------------------------------------------------------------------===//
//
// HwtFpga spmd/simt execution.
//
//===----------------------------------------------------------------------===//

namespace llvm {

bool HwtFpgaTTIImpl::hasBranchDivergence() {
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

bool HwtFpgaTTIImpl::isSourceOfDivergence(const Value *V) {
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
// HwtFpga cost model.
//
//===----------------------------------------------------------------------===//

InstructionCost HwtFpgaTTIImpl::getIntImmCostInst(unsigned Opcode,
		unsigned Idx, const APInt &Imm, Type *Ty, TTI::TargetCostKind CostKind,
		Instruction *Inst) const {
	switch (Opcode) {
	// Bit functions are free
	case Instruction::BitCast:
	case Instruction::IntToPtr:
	case Instruction::PtrToInt:
	case Instruction::Trunc:
		return TTI::TCC_Free;
	case Instruction::Load:
	case Instruction::Store:
		return TTI::TCC_Expensive;
	case Instruction::Call:
		if (auto CI = dyn_cast<CallInst>(Inst)) {
			if (hwtHls::IsBitRangeGet(CI) || hwtHls::IsBitConcat(CI))
				return TTI::TCC_Free;
		}
		return TTI::TCC_Expensive;
	case Instruction::ICmp:
		if (Ty->getIntegerBitWidth() > 1)
			return TTI::TCC_Basic;
		else
			return TTI::TCC_Free;
	default:
		return TTI::TCC_Basic;
	}
}

// Any immediate value can be synthesized
bool HwtFpgaTTIImpl::isLegalAddImmediate(int64_t Imm) const {
	return true;
}
bool HwtFpgaTTIImpl::isLegalICmpImmediate(int64_t Imm) const {
	return true;
}

// Masked memory operations are free
bool HwtFpgaTTIImpl::isLegalMaskedStore(Type *DataType, Align Alignment) const {
	return true;
}
bool HwtFpgaTTIImpl::isLegalMaskedLoad(Type *DataType, Align Alignment) const {
	return true;
}

bool HwtFpgaTTIImpl::isTruncateFree(Type *Ty1, Type *Ty2) const {
	if (!Ty1->isIntegerTy() || !Ty2->isIntegerTy())
		return false;
	unsigned NumBits1 = Ty1->getPrimitiveSizeInBits();
	unsigned NumBits2 = Ty2->getPrimitiveSizeInBits();
	return NumBits1 > NumBits2;
}

bool HwtFpgaTTIImpl::isTypeLegal(Type *Ty) const {
	if (Ty->isIntegerTy())
		return true;
	else
		return false;
}

bool HwtFpgaTTIImpl::shouldBuildLookupTables() const {
	return true; // this must be true to translate SwitchInst to Load from global constant for llvm-16.0.0
	//return false; // no lookup tables for jumps
}

bool HwtFpgaTTIImpl::shouldBuildLookupTablesForConstant(Constant * C) const {
	return true;
}

TargetTransformInfo::PopcntSupportKind HwtFpgaTTIImpl::getPopcntSupport(
		unsigned IntTyWidthInBit) {
	return TTI::PSK_FastHardware;
}

unsigned HwtFpgaTTIImpl::getNumberOfRegisters(unsigned ClassID) const {
	return std::numeric_limits<unsigned>::max() >> 2;
}

TypeSize HwtFpgaTTIImpl::getRegisterBitWidth(bool Vector) const {
	return TypeSize::getScalable(std::numeric_limits<unsigned>::max() >> 2);
}

InstructionCost HwtFpgaTTIImpl::getShuffleCost(TTI::ShuffleKind Kind, VectorType *Ty, ArrayRef<int> Mask,
        TTI::TargetCostKind CostKind, int Index, VectorType *SubTp,
        ArrayRef<const Value *> Args) const {
	return TTI::TCC_Free;
}

InstructionCost HwtFpgaTTIImpl::getCastInstrCost(unsigned Opcode, Type *Dst,
		Type *Src, TTI::CastContextHint CCH, TTI::TargetCostKind CostKind,
		const Instruction *I) const {
	return TTI::TCC_Free;
}

InstructionCost HwtFpgaTTIImpl::getExtractWithExtendCost(unsigned Opcode,
		Type *Dst, VectorType *VecTy, unsigned Index) const {
	return TTI::TCC_Free;
}

InstructionCost HwtFpgaTTIImpl::getVectorInstrCost(unsigned Opcode, Type *Val,
        TTI::TargetCostKind CostKind,
        unsigned Index, Value *Op0,
        Value *Op1) const {
	return TTI::TCC_Free;
}

InstructionCost HwtFpgaTTIImpl::getVectorInstrCost(const Instruction &I, Type *Val,
                                   TTI::TargetCostKind CostKind,
                                   unsigned Index) const {
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
	if (auto CI = dyn_cast<CallInst>(U)) {
		if (hwtHls::IsBitRangeGet(CI) || hwtHls::IsBitConcat(CI))
			return true;
	}

	auto Opcode = O->getOpcode();

	// Bitwise operator with constant on RHS is definitely free.
	// Notice that a free bitwise operator is not necessary having a constant RHS
	Value *RHS = *std::prev(U->op_end());
	if (IsBitwiseBinaryOperator(Opcode) && isa<Constant>(RHS))
		return true;

	return false;
}

InstructionCost HwtFpgaTTIImpl::getInstructionCost(const User *U,
                                   ArrayRef<const Value *> Operands,
                                   TTI::TargetCostKind CostKind) {
	if (IsFreeOperator(U))
		return TTI::TCC_Free;
	if (!TM->getAllowVolatileMemOpDuplication()) {
		if (CostKind == TTI::TargetCostKind::TCK_CodeSize
				|| CostKind == TTI::TargetCostKind::TCK_Latency
				|| CostKind == TTI::TargetCostKind::TCK_SizeAndLatency) {
			// minimize duplication of volatile loads and stores
			if (const StoreInst *S = dyn_cast<StoreInst>(U)) {
				if (S->isVolatile())
					return InstructionCost::getInvalid();
			}
			if (const LoadInst *L = dyn_cast<LoadInst>(U)) {
				if (L->isVolatile())
					return InstructionCost::getInvalid();
			}
		}
	}
	return BaseT::getInstructionCost(U, Operands, CostKind);
}

void HwtFpgaTTIImpl::getUnrollingPreferences(Loop*, ScalarEvolution&,
		TTI::UnrollingPreferences& UP, OptimizationRemarkEmitter*) const {
	// (unroll nothing by default but allow all)
	UP.Threshold = 1;
	UP.PartialThreshold = 1;
	UP.Count = 0;
	UP.MaxCount = UINT_MAX;
	UP.FullUnrollMaxCount = UINT_MAX;
	UP.Partial = true;
	UP.Runtime = false;
	UP.AllowRemainder = true;
}

Type* HwtFpgaTTIImpl::getMemcpyLoopLoweringType(LLVMContext &Context,
		Value *Length, unsigned SrcAddrSpace, unsigned DestAddrSpace,
		unsigned SrcAlign, unsigned DestAlign, std::optional<uint32_t> AtomicElementSize) const {
	uint64_t Min = MinAlign(SrcAlign, DestAlign);
	KnownBits KB = computeKnownBits(Length, getDataLayout());
	Min = MinAlign(Min, 1 << KB.countMinTrailingZeros());
	return IntegerType::get(Context, 8 * Min);
}

unsigned HwtFpgaTTIImpl::getLoadStoreVecRegBitWidth(
		unsigned AddrSpace) const {
	return 1 << 16;
}

bool HwtFpgaTTIImpl::isLegalToVectorizeLoadChain(unsigned ChainSizeInBytes,
		Align Alignment, unsigned AddrSpace) const {
	return true;
}

bool HwtFpgaTTIImpl::isLegalToVectorizeStoreChain(unsigned ChainSizeInBytes,
		Align Alignment, unsigned AddrSpace) const {
	return true;
}
}
