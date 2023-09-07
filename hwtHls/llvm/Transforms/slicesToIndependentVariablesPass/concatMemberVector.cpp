#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/concatMemberVector.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/utils.h>

using namespace llvm;

namespace hwtHls {

bool OffsetWidthValue::operator==(const OffsetWidthValue &rhs) const {
	return this->offset == rhs.offset && this->width == rhs.width && this->value == rhs.value;
}
bool OffsetWidthValue::operator<(OffsetWidthValue &other) const {
	return offset < other.offset;
}

void OffsetWidthValue::print(llvm::raw_ostream &OS) const {
	OS << *this->value << " [off=" << offset << ", w=" << width << "]";
}

OffsetWidthValue OffsetWidthValue::fromValue(Value * V) {
	if (auto* CI = dyn_cast<CallInst>(V)) {
		if (IsBitRangeGet(CI)) {
			return BitRangeGetOffsetWidthValue(CI);
		}
	}
	return {0, V->getType()->getIntegerBitWidth(), V};
}

Value* ConcatMemberVector::_memberToValue(OffsetWidthValue &item) {
	bool fitsExactly = item.width == item.value->getType()->getIntegerBitWidth() && item.offset == 0;
	if (fitsExactly) {
		return item.value;
	} else if (auto *C = dyn_cast<ConstantInt>(item.value)) {
		return builder.getInt(C->getValue().lshr(item.offset).trunc(item.width));
	} else {
		if (commonSubexpressionCache){
			auto existing = commonSubexpressionCache->find(item);
			if (existing != commonSubexpressionCache->end())
				return existing->second;
		}
		// create bit range get just behind the source of original bit-vector which is being sliced
		auto insertPoint = builder.GetInsertPoint();
		Instruction* itemInstr = dyn_cast<Instruction>(item.value);
		bool insertPointWasOnValue = (insertPoint != builder.GetInsertBlock()->end() &&
				insertPoint.getNodePtr() == itemInstr);
		builder.SetInsertPoint(itemInstr);
		builder.SetInsertPoint(builder.GetInsertBlock(), ++builder.GetInsertPoint());
		IRBuilder_setInsertPointBehindPhi(builder, &*builder.GetInsertPoint());
		auto *res = CreateBitRangeGetConst(&builder, item.value, item.offset, item.width);
		if (commonSubexpressionCache) {
			(*commonSubexpressionCache)[item] = res;
		}
		if (!insertPointWasOnValue && insertPoint.getNodePtr() != nullptr) {
			builder.SetInsertPoint(&*insertPoint);
		}
		return res;
	}
}

ConcatMemberVector::ConcatMemberVector(IRBuilder<> &_builder,
		std::unordered_map<OffsetWidthValue, Value*> *_commonSubexpressionCache) :
		builder(_builder), commonSubexpressionCache(_commonSubexpressionCache) {
}

void ConcatMemberVector::push_back(OffsetWidthValue item) {
	auto *C1 = dyn_cast<ConstantInt>(item.value);
	if (C1) {
		assert(item.offset == 0);
		assert(C1->getType()->getIntegerBitWidth() == item.width);
	}
	if (members.size()) {
		OffsetWidthValue &last = members.back();
		if (last.value == item.value && last.offset + last.width == item.offset) {
			// if it is consecutive slice, merge it
			last.width += item.width;
			return;
		}
		auto *C0 = dyn_cast<ConstantInt>(last.value);
		if (C0 && C1) {
			// merge constants
			auto w = last.width + item.width;
			last.value = builder.getInt(C0->getValue().zext(w) | C1->getValue().zext(w).shl(last.width));
			last.width += item.width;
			return;
		}
	}
	members.push_back(item);
}

Value* ConcatMemberVector::resolveValue(Instruction *builderPosition) {
	if (members.size() == 1) {
		return _memberToValue(members[0]);
	} else {
		assert(
				builderPosition != nullptr
						&& "builderPosition must be set to an instruction where the computation of result value should be placed");
		SmallVector<Value*> concatMembers;
		concatMembers.reserve(members.size());
		for (auto &m : members) {
			concatMembers.push_back(_memberToValue(m));
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
	return res;
}

}
