#include "concatMemberVector.h"
#include "../../targets/intrinsic/bitrange.h"

using namespace llvm;

namespace hwtHls {

bool OffsetWidthValue::operator==(const OffsetWidthValue &rhs) const {
	return this->offset == rhs.offset && this->width == rhs.width
			&& this->value == rhs.value;
}

Value* ConcatMemberVector::_memberToValue(OffsetWidthValue &item) {
	bool fitsExactly = item.width == item.value->getType()->getIntegerBitWidth()
			&& item.offset == 0;
	if (fitsExactly) {
		return item.value;
	} else if (auto *C = dyn_cast<ConstantInt>(item.value)) {
		return builder.getInt(C->getValue().lshr(item.offset).trunc(item.width));
	} else {

		auto existing = commonSubexpressionCache.find(item);
		if (existing != commonSubexpressionCache.end())
			return existing->second;
		builder.SetInsertPoint(dyn_cast<Instruction>(item.value));
		builder.SetInsertPoint(builder.GetInsertBlock(),
				++builder.GetInsertPoint());
		auto *res = CreateBitRangeGet(&builder, item.value,
				builder.getInt64(item.offset), item.width);
		commonSubexpressionCache[item] = res;
		return res;
	}
}
/*
 * :ivar members: lower bits first arguments for a bit concatenation
 * */

ConcatMemberVector::ConcatMemberVector(IRBuilder<> &_builder,
		std::unordered_map<OffsetWidthValue, Value*> &_commonSubexpressionCache) :
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
			last.value = builder.getInt(
					C0->getValue().zext(w)
							| C1->getValue().zext(w).shl(last.width));
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
		builder.SetInsertPoint(builderPosition);
		return CreateBitConcat(&builder, concatMembers);
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
