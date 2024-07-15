#pragma once

#include <optional>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/KnownBits.h>

namespace hwtHls {

class KnownValue {
public:
	llvm::Value *V; // if V is nullptr it means that KB holds the value, if it is not it is the value and KB should be ignored
	llvm::KnownBits KB;
	KnownValue();
	KnownValue(const KnownValue &other);
	KnownValue(unsigned bitwidth);
	KnownValue(llvm::KnownBits KB);
	KnownValue(std::optional<bool> VResolved, llvm::Value &_V);
	KnownValue(llvm::ConstantInt &V);
	KnownValue(llvm::Value &V);
	static KnownValue get1bVal(bool val);
	static KnownValue compute(llvm::Value &V);
	bool hasNoSpecificConstValue() const;
	bool isZero() const;
	bool isNonZero() const;
	KnownValue resolveICmp(llvm::ICmpInst::Predicate pred, const KnownValue &o1,
			llvm::ICmpInst *CurVal) const;
	KnownValue resolveSelect(const KnownValue &oT, const KnownValue &oF,
			llvm::SelectInst &CurVal) const;
	KnownValue resolveAnd(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveOr(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveXor(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveLShr(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveAShr(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveShl(const KnownValue &o1, llvm::Instruction &CurVal) const;
	KnownValue resolveSExt(const KnownValue &o1, llvm::SExtInst &CurVal) const;
	KnownValue resolveZExt(const KnownValue &o1, llvm::ZExtInst &CurVal) const;
	KnownValue resolveBitCast(const KnownValue &o1, llvm::BitCastInst &CurVal) const;
	static KnownValue resolveBitConcat(const llvm::SmallVectorImpl<KnownValue> &Ops,
			llvm::CallInst &CurVal);
	KnownValue resolveBitRangeGet(const KnownValue &o1,
			llvm::CallInst &CurVal) const;
};

// :attention: InBlockValues does not contain records for values defined outside of block
using InBlockValues = std::unordered_map<llvm::Instruction *, KnownValue>;
// :attention: InBlockValuesStack does not contain values defined outside of parent loops or in child loops
using InBlockValuesStack = std::vector<InBlockValues>;

KnownValue findValueInStack(const InBlockValuesStack &frameStack, llvm::Value *V);

class PushNewBlockValueFrame {
	InBlockValuesStack &frameStack;
	llvm::BasicBlock &BB;
public:
	PushNewBlockValueFrame(InBlockValuesStack &frameStack, llvm::BasicBlock &PredBB,
			llvm::BasicBlock &BB);
	~PushNewBlockValueFrame();
};


}
