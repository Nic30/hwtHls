#include <hwtHls/llvm/Transforms/PruneLoopPhiDeadIncomingValuesPass/KnownValue.h>
#include <llvm/IR/Constants.h>
#include <llvm/ADT/STLExtras.h>

using namespace llvm;
namespace hwtHls {

KnownValue::KnownValue() :
		V(nullptr), KB(1) {
}
KnownValue::KnownValue(const KnownValue &other) :
		V(other.V), KB(other.KB) {
}
KnownValue::KnownValue(unsigned bitwidth) :
		V(nullptr), KB(bitwidth) {
}
KnownValue::KnownValue(KnownBits KB) :
		V(nullptr), KB(KB) {
}
KnownValue::KnownValue(std::optional<bool> VResolved, Value &_V) :
		V(&_V), KB(1) {
	if (VResolved.has_value()) {
		V = nullptr;
		if (VResolved.value())
			KB.One = 1;
		else
			KB.Zero = 1;
	}
}
KnownValue::KnownValue(ConstantInt &V) :
		V(nullptr), KB(KnownBits::makeConstant(V.getValue())) {
}
KnownValue::KnownValue(Value &V) :
		V(&V), KB(
				V.getType()->isIntegerTy() ?
						V.getType()->getIntegerBitWidth() : 1) {
	assert(
			!isa<ConstantData>(&V)
					&& "Check that this is not undef, poison or any other special const");
}
KnownValue KnownValue::get1bVal(bool val) {
	KnownValue res(1);
	if (val)
		res.KB.One = 1;
	else
		res.KB.Zero = 1;
	return res;
}
KnownValue KnownValue::compute(Value &V) {
	if (auto CI = dyn_cast<ConstantInt>(&V)) {
		return KnownValue(*CI);
	} else {
		return KnownValue(V);
	}
}
bool KnownValue::hasNoSpecificConstValue() const {
	return V || (KB.One == 0 && KB.Zero == 0);
}
bool KnownValue::isZero() const {
	return !V && KB.isZero();
}
bool KnownValue::isNonZero() const {
	return !V && KB.isNonZero();
}
KnownValue KnownValue::resolveICmp(ICmpInst::Predicate pred,
		const KnownValue &o1, ICmpInst *CurVal) const {
	bool hasSameVal = V && V == o1.V;
	bool hasKnownVal = !V && !o1.V;
	bool valIfSame;
	std::function<std::optional<bool>(const KnownBits&, const KnownBits&)> predicate;
	switch (pred) {
	case ICmpInst::Predicate::ICMP_EQ: {
		valIfSame = true;
		predicate = KnownBits::eq;
		break;
	}
	case ICmpInst::Predicate::ICMP_NE: {
		valIfSame = false;
		predicate = KnownBits::ne;
		break;
	}
	case ICmpInst::Predicate::ICMP_UGT: {
		valIfSame = false;
		predicate = KnownBits::ugt;
		break;
	}
	case ICmpInst::Predicate::ICMP_UGE: {
		valIfSame = true;
		predicate = KnownBits::uge;
		break;
	}
	case ICmpInst::Predicate::ICMP_ULT: {
		valIfSame = false;
		predicate = KnownBits::ult;
		break;
	}
	case ICmpInst::Predicate::ICMP_ULE: {
		valIfSame = true;
		predicate = KnownBits::ule;
		break;
	}
	case ICmpInst::Predicate::ICMP_SGT: {
		valIfSame = false;
		predicate = KnownBits::sgt;
		break;
	}
	case ICmpInst::Predicate::ICMP_SGE: {
		valIfSame = true;
		predicate = KnownBits::sge;
		break;
	}
	case ICmpInst::Predicate::ICMP_SLT: {
		valIfSame = false;
		predicate = KnownBits::slt;
		break;
	}
	case ICmpInst::Predicate::ICMP_SLE: {
		valIfSame = true;
		predicate = KnownBits::sle;
		break;
	}
	default:
		llvm_unreachable("NotImplementedError: unsupported predicate");
	}

	if (hasSameVal) {
		return KnownValue::get1bVal(valIfSame);
	} else if (hasKnownVal) {
		return KnownValue(predicate(KB, o1.KB), *CurVal);
	} else {
		if (CurVal)
			return KnownValue(*CurVal);
		else
			return KnownValue(1); // 1b undef
	}
}

KnownValue KnownValue::resolveSelect(const KnownValue &oT, const KnownValue &oF,
		SelectInst &CurVal) const {
	if (V || KB.isUnknown()) {
		return KnownValue(CurVal);
	} else {
		assert(KB.isConstant());
		if (KB.isAllOnes()) {
			return oT;
		} else {
			return oF;
		}
	}
}
KnownValue KnownValue::resolveAnd(const KnownValue &o1,
		Instruction &CurVal) const {
	if (V && V == o1.V) {
		return *this;
	} else if (!V && !o1.V) {
		auto _KB = KB;
		_KB &= o1.KB;
		return KnownValue(std::move(_KB));
	}
	return KnownValue(CurVal);
}
KnownValue KnownValue::resolveOr(const KnownValue &o1,
		Instruction &CurVal) const {
	if (V && V == o1.V) {
		return *this;
	} else if (!V && !o1.V) {
		auto _KB = KB;
		_KB |= o1.KB;
		return KnownValue(std::move(_KB));
	}
	return KnownValue(CurVal);
}
KnownValue KnownValue::resolveXor(const KnownValue &o1,
		Instruction &CurVal) const {
	if (!V && !o1.V) {
		KnownBits _KB = KB;
		_KB |= o1.KB;
		return KnownValue(std::move(_KB));
	}
	return KnownValue(CurVal);
}

KnownValue KnownValue::resolveLShr(const KnownValue &o1,
		Instruction &CurVal) const {
	if (!o1.V && o1.KB.isZero()) {
		return *this;
	} else if (!V && !o1.V) {
		return KnownValue(KnownBits::lshr(KB, o1.KB));
	}
	return KnownValue(CurVal);
}
KnownValue KnownValue::resolveAShr(const KnownValue &o1,
		Instruction &CurVal) const {
	if (!o1.V && o1.KB.isZero()) {
		return *this;
	} else if (!V && !o1.V) {
		return KnownValue(KnownBits::ashr(KB, o1.KB));
	}
	return KnownValue(CurVal);
}
KnownValue KnownValue::resolveShl(const KnownValue &o1,
		Instruction &CurVal) const {
	if (!o1.V && o1.KB.isZero()) {
		return *this;
	} else if (!V && !o1.V) {
		return KnownValue(KnownBits::shl(KB, o1.KB));
	}
	return KnownValue(CurVal);
}
KnownValue KnownValue::resolveSExt(const KnownValue &o1,
		SExtInst &CurVal) const {
	size_t BitWidth = CurVal.getType()->getIntegerBitWidth();
	KnownValue tmp = *this;
	tmp.KB = tmp.KB.sext(BitWidth);
	if (V) {
		tmp.V = &CurVal;
	}
	return tmp;

}
KnownValue KnownValue::resolveZExt(const KnownValue &o1,
		ZExtInst &CurVal) const {
	size_t BitWidth = CurVal.getType()->getIntegerBitWidth();
	KnownValue tmp = *this;
	tmp.KB = tmp.KB.zext(BitWidth);
	if (V) {
		tmp.V = &CurVal;
	}
	return tmp;

}
KnownValue KnownValue::resolveBitCast(const KnownValue &o1,
		BitCastInst &CurVal) const {
	return *this;
}
KnownValue KnownValue::resolveBitConcat(const SmallVectorImpl<KnownValue> &Ops,
		CallInst &CurVal) {
	KnownValue res(CurVal.getType()->getIntegerBitWidth());
	size_t offset = 0;
	for (auto O : Ops) {
		res.KB.insertBits(O.KB, offset);
		offset += O.KB.getBitWidth();
	}
	if (!res.KB.isConstant()) {
		res.V = &CurVal;
	}
	return res;
}
KnownValue KnownValue::resolveBitRangeGet(const KnownValue &o1,
		CallInst &CurVal) const {
	size_t BitWidth = CurVal.getType()->getIntegerBitWidth();
	KnownValue res(BitWidth);
	if (o1.KB.isConstant()) {
		size_t BitPosition = o1.KB.getConstant().getZExtValue();
		res.KB = KB.extractBits(BitWidth, BitPosition);
		if (V) {
			res.V = &CurVal;
		}
	} else {
		res.V = &CurVal;
	}
	return res;
}

KnownValue findValueInStack(const InBlockValuesStack &frameStack, Value *V) {
	if (auto CI = dyn_cast<ConstantInt>(V)) {
		return KnownValue(*CI);
	} else if (isa<ConstantData>(V)) {
		// undef, poison and others
		return KnownValue(V->getType()->getIntegerBitWidth());
	}
	if (auto I = dyn_cast<Instruction>(V)) {
		for (auto &Values : reverse(frameStack)) {
			auto KV = Values.find(I);
			if (KV != Values.end())
				return KV->second;
		}
	}
	return KnownValue(*V);
}

PushNewBlockValueFrame::PushNewBlockValueFrame(InBlockValuesStack &frameStack,
		BasicBlock &PredBB, BasicBlock &BB) :
		frameStack(frameStack), BB(BB) {
	InBlockValues inBlockVals;
	for (PHINode &PHI : BB.phis()) {
		auto V = PHI.getIncomingValueForBlock(&PredBB);
		inBlockVals[&PHI] = findValueInStack(frameStack, V);
	}
	frameStack.push_back(std::move(inBlockVals));
}
PushNewBlockValueFrame::~PushNewBlockValueFrame() {
	frameStack.pop_back();
}

}
