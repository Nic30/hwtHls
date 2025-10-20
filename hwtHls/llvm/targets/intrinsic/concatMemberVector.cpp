#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>

using namespace llvm;

namespace hwtHls {

bool OffsetWidthValue::operator==(const OffsetWidthValue &rhs) const {
	return this->offset == rhs.offset && this->width == rhs.width
			&& this->value == rhs.value;
}
bool OffsetWidthValue::operator<(OffsetWidthValue &other) const {
	return offset < other.offset;
}
bool OffsetWidthValue::contains(const OffsetWidthValue &other) const {
	return offset <= other.offset
			&& offset + width >= other.offset + other.width;
}
void OffsetWidthValue::print(llvm::raw_ostream &OS) const {
	OS << *this->value << " [off=" << offset << ", w=" << width << "]";
}

OffsetWidthValue OffsetWidthValue::fromValue(Value *V) {
	if (auto *CI = dyn_cast<CallInst>(V)) {
		if (IsBitRangeGet(CI)) {
			return BitRangeGetOffsetWidthValue(CI);
		}
	} else if (auto *TI = dyn_cast<TruncInst>(V)) {
		return BitRangeGetOffsetWidthValue(TI);
	}
	// default case, build OffsetWidthValue equal to original V
	auto Ty = V->getType();
	return {0, Ty->isIntegerTy() ? Ty->getIntegerBitWidth() : 1, V};
}

bool OffsetWidthValue::isMsbOf(const llvm::Value *v) const {
	if (width == 1) {
		if (value == v && offset == v->getType()->getIntegerBitWidth() - 1) {
			// this is an extract of msb from v
			return true;
		}
		if (auto vAsSExt = dyn_cast<SExtInst>(v)) {
			auto srcV = vAsSExt->getOperand(0);
			if (value == v && offset >= srcV->getType()->getIntegerBitWidth() - 1) {
				// this is an extract of msb from SExt
				return true;
			} else if (value == srcV && offset == srcV->getType()->getIntegerBitWidth() - 1) {
				// this is an extract of msb directly from srcV operand of v which is SExtInst
				return true;
			}
		} else {
			auto vOWV = OffsetWidthValue::fromValue(const_cast<Value*>(v));
			if (value == vOWV.value && offset == vOWV.offset + vOWV.width - 1) {
				// the v itself is some sort of extract from same vector and msb is same bit as this
				return true;
			}
		}
	}
	return false;
}

bool OffsetWidthValue::isIdentity() const {
	auto Ty = value->getType();
	return offset == 0
			&& width == (Ty->isIntegerTy() ? Ty->getIntegerBitWidth() : 1);
}

void OffsetWidthValue::normalize() {
	if (isa<ConstantData>(value) && value->getType()->isIntegerTy()
			&& value->getType()->getIntegerBitWidth() != width) {
		auto newTy = IntegerType::get(value->getContext(), width);
		if (isa<PoisonValue>(value)) {
			value = PoisonValue::get(newTy);
			offset = 0;
		} else if (isa<UndefValue>(value)) {
			value = UndefValue::get(newTy);
			offset = 0;
		} else if (auto CI = dyn_cast<ConstantInt>(value)) {
			auto v = CI->getValue().extractBits(width, offset);
			value = ConstantInt::get(newTy, v);
			offset = 0;
		}
	}
}

Value* ConcatMemberVector::_memberToValue(IRBuilderBase &builder,
		std::unordered_map<OffsetWidthValue, llvm::Value*> *commonSubexpressionCache,
		OffsetWidthValue &item) {
	bool fitsExactly = item.width == item.value->getType()->getIntegerBitWidth()
			&& item.offset == 0;
	if (fitsExactly) {
		return item.value;
	} else if (auto *C = dyn_cast<ConstantInt>(item.value)) {
		return builder.getInt(C->getValue().lshr(item.offset).trunc(item.width));
	} else {
		if (commonSubexpressionCache) {
			auto existing = commonSubexpressionCache->find(item);
			if (existing != commonSubexpressionCache->end())
				return existing->second;
		}
		// create bit range get just behind the source of original bit-vector which is being sliced
		auto insertPoint = builder.GetInsertPoint();
		Instruction *itemInstr = dyn_cast<Instruction>(item.value);
		bool insertPointWasOnValue = (insertPoint
				!= builder.GetInsertBlock()->end()
				&& insertPoint.getNodePtr() == itemInstr);
		builder.SetInsertPoint(itemInstr);
		builder.SetInsertPoint(builder.GetInsertBlock(),
				++builder.GetInsertPoint());
		IRBuilder_setInsertPointBehindPhi(builder, &*builder.GetInsertPoint());
		auto *res = CreateBitRangeGetConst(&builder, item.value, item.offset,
				item.width);
		if (commonSubexpressionCache) {
			(*commonSubexpressionCache)[item] = res;
		}
		if (!insertPointWasOnValue && insertPoint.getNodePtr() != nullptr) {
			builder.SetInsertPoint(&*insertPoint);
		}
		return res;
	}
}

void ConcatMemberVector::push_back_Value(llvm::Value *item) {
	push_back(OffsetWidthValue::fromValue(item));
}

void ConcatMemberVector::push_back(OffsetWidthValue item) {
	auto *C1 = dyn_cast<ConstantInt>(item.value);
	if (C1) {
		assert(item.offset == 0);
		assert(C1->getType()->getIntegerBitWidth() == item.width);
	}
	if (members.size()) {
		OffsetWidthValue &last = members.back();
		if (last.value == item.value
				&& last.offset + last.width == item.offset) {
			// if it is consecutive slice, merge it
			last.width += item.width;
			return;
		}
		auto *C0 = dyn_cast<ConstantInt>(last.value);
		if (C0 && C1) {
			// merge constants
			auto w = last.width + item.width;
			last.value = ConstantInt::get(C0->getContext(),
					C0->getValue().zext(w)
							| C1->getValue().zext(w).shl(last.width));
			last.width += item.width;
			return;
		}
	}
	members.push_back(item);
}

void ConcatMemberVector::push_back_flattened(Value *operand) {
	if (auto CI = dyn_cast<CallInst>(operand)) {
		if (IsBitConcat(CI)) {
			for (auto &A : CI->args()) {
				push_back_flattened(A.get());
			}
			return;
		}
	}
	push_back(OffsetWidthValue::fromValue(operand));
}


bool ConcatMemberVector::isLsbBitsOf(const ConcatMemberVector &other) const {
	auto thisIt = members.begin();
	for (auto m : other.members) {
		if (thisIt == members.end())
			return false;
		if (*thisIt != m)
			return false;
		++thisIt;
	}
	return true;
}

bool ConcatMemberVector::isMsbBitsOf(const ConcatMemberVector &other) const {
	auto thisIt = members.rbegin();
	for (auto m : llvm::reverse(other.members)) {
		if (thisIt == members.rend())
			return false;
		if (*thisIt != m)
			return false;
		++thisIt;
	}
	return true;
}

Value* ConcatMemberVector::resolveValue(IRBuilderBase &builder,
		std::unordered_map<OffsetWidthValue, llvm::Value*> *commonSubexpressionCache,
		Instruction *builderPosition) {
	if (members.size() == 1) {
		return _memberToValue(builder, commonSubexpressionCache, members[0]);
	} else {
		assert(
				builderPosition != nullptr
						&& "builderPosition must be set to an instruction where the computation of result value should be placed");
		SmallVector<Value*> concatMembers;
		concatMembers.reserve(members.size());
		for (auto &m : members) {
			concatMembers.push_back(
					_memberToValue(builder, commonSubexpressionCache, m));
		}
		IRBuilder_setInsertPointBehindPhi(builder, builderPosition);
		auto res = CreateBitConcat(&builder, concatMembers);
		return res;
	}
}

uint64_t ConcatMemberVector::width() {
	uint64_t res = 0;
	for (OffsetWidthValue &m : members) {
		res += m.width;
	}
	return res;
}

OffsetWidthValue BitRangeGetOffsetWidthValue(CallInst *C) {
	OffsetWidthValue res;
	res.value = C->getArgOperand(0);
	const auto *_offset = dyn_cast<ConstantInt>(C->getArgOperand(1));
	assert(_offset && "Offset must be a constant");
	res.offset = _offset->getZExtValue();
	res.width = C->getType()->getIntegerBitWidth();
	res.normalize();
	return res;
}

OffsetWidthValue BitRangeGetOffsetWidthValue(TruncInst *T) {
	OffsetWidthValue res;
	res.value = T->getOperand(0);
	res.offset = 0;
	res.width = T->getType()->getIntegerBitWidth();
	res.normalize();
	return res;
}

}
