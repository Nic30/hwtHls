#include <hwtHls/llvm/Transforms/utils/bitSliceFlattening.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

using namespace llvm;

namespace hwtHls {

// for params meaning see collectConcatMembers
inline bool collectConcatMembersAsItIs(Value *v,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
		uint64_t widthOfIRes) {
	size_t unusedPrefixWidth = 0;
	bool didModify = false;
	if (mainOffset > currentOffset) {
		didModify = true;
		unusedPrefixWidth = mainOffset - currentOffset;
		if (widthOfIRes <= unusedPrefixWidth) {
			// skipping this member entirely because it is the unused prefix
			return didModify;
		}
		//widthOfIRes -= unusedPrefixWidth;
		//currentOffset += unusedPrefixWidth;
		offsetOfIRes += unusedPrefixWidth;
	}
	uint64_t mainEnd = mainOffset + mainWidth;
	// take slice from this instruction as it is
	uint64_t bitsToTake = std::min((widthOfIRes - unusedPrefixWidth), /* available in "v"*/
	mainEnd - currentOffset /*remaining from main requested*/);
	assert(
			bitsToTake > 0
					&& "If it is 0 this function should not be called in the first place");

	currentOffset += widthOfIRes; // this may result in possition behind main slice but it is intended
	// as currentOffset is a position for processing and we processed this member v
	members.push_back(
			ConcatMember { v, offsetOfIRes, widthOfIRes, bitsToTake });
	return didModify;
}

bool collectConcatMembersSlice(llvm::Instruction *ParentI, size_t &subSliceOffset,
		Value *_src, std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
		uint64_t widthOfIRes, bool &didReduce) {
	uint64_t subSliceResWidth = ParentI->getType()->getIntegerBitWidth();
	subSliceOffset += offsetOfIRes;
	if (widthOfIRes > subSliceResWidth) {
		errs() << *ParentI << " widthOfIRes:" << widthOfIRes << "\n";
		llvm_unreachable(
				"extract bits provides value of less bits than expected");
	}
	bool isBitRangeGetOnBitRangeGet = false;
	bool mayContainOtherSlicesAndConcats = false;
	if (auto *src = dyn_cast<CallInst>(_src)) {
		// look trough the source operand of this extract instruction
		isBitRangeGetOnBitRangeGet = IsBitRangeGet(src);
		mayContainOtherSlicesAndConcats = isBitRangeGetOnBitRangeGet
				|| IsBitConcat(src);
	} else if (isa<TruncInst>(ParentI)) {
		isBitRangeGetOnBitRangeGet = true;
		mayContainOtherSlicesAndConcats = true;
	} else if (isa<ZExtInst>(ParentI) || isa<SExtInst>(ParentI)) {
		isBitRangeGetOnBitRangeGet = false;
		mayContainOtherSlicesAndConcats = true;
	}

	if (mayContainOtherSlicesAndConcats) {
		didReduce = collectConcatMembers(_src, members, mainOffset, mainWidth,
				currentOffset, subSliceOffset, subSliceResWidth)
				|| isBitRangeGetOnBitRangeGet;
		assert(members.size());
		auto &lastAdded = members.back();
		didReduce |= lastAdded.v != _src;
		return true;
	}
	return false;
}

bool collectConcatMembersStackConcatMember(llvm::Value *V,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, size_t mainEnd, uint64_t &currentOffset,
		uint64_t &offsetOfIRes, uint64_t widthOfIRes, bool &didReduce,
		size_t argI, size_t argSize) {
	// [todo] check if thisMemberOffset is computed correctly for more than 2 operands
	uint64_t thisMemberOffset = 0;
	uint64_t width = V->getType()->getIntegerBitWidth();
	if (offsetOfIRes) {
		if (offsetOfIRes > width) {
			thisMemberOffset = width;
			offsetOfIRes -= width;
			width = 0;
		} else {
			thisMemberOffset = offsetOfIRes;
			width -= offsetOfIRes;
			offsetOfIRes = 0;
		}
	}
	if (currentOffset + width < mainOffset || width == 0) {
		didReduce = true;
		currentOffset += width;
		// skipping the unused prefix
	} else {
		// can look trough
		didReduce |= collectConcatMembers(V, members, mainOffset, mainWidth,
				currentOffset, thisMemberOffset, width);

	}
	if (currentOffset >= mainEnd) {
		// we do not care about successors because parent EXTRACT does not select them
		didReduce |= argI != argSize - 1;
		return true;
	}
	return false;
}

bool collectConcatMembers(llvm::Value *_v, std::vector<ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &currentOffset,
		uint64_t offsetOfIRes, uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	if (auto *CI = dyn_cast<CallInst>(_v)) {
		if (IsBitConcat(CI)) {
			// e.g. %1 = call i10 @hwtHls.bitConcat.i8.i2(i8 %0, i2 -1)
			bool didReduce = false;
			size_t argI = 0;
			for (auto &_arg : CI->args()) {
				auto *arg = _arg.get();
				if (collectConcatMembersStackConcatMember(arg, members,
						mainOffset, mainWidth, mainEnd, currentOffset,
						offsetOfIRes, widthOfIRes, didReduce, argI,
						CI->arg_size()))
					break;
				++argI;
			}
			return didReduce;
		} else if (IsBitRangeGet(CI)) {
			// e.g. %1 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %1, i5 0)
			if (auto _subSliceOffset = dyn_cast<ConstantInt>(
					CI->getArgOperand(1))) {
				uint64_t subSliceOffset = _subSliceOffset->getZExtValue();
				auto *_src = CI->getArgOperand(0);
				bool didReduce = false;
				if (collectConcatMembersSlice(CI, subSliceOffset, _src, members,
						mainOffset, mainWidth, currentOffset, offsetOfIRes,
						widthOfIRes, didReduce))
					return didReduce;
			}
		}
	} else if (auto TI = dyn_cast<TruncInst>(_v)) {
		uint64_t subSliceOffset = 0;
		auto *_src = TI->getOperand(0);
		bool didReduce = false;
		collectConcatMembersSlice(CI, subSliceOffset, _src, members, mainOffset,
				mainWidth, currentOffset, offsetOfIRes, widthOfIRes, didReduce);
		return didReduce;

	} else if (auto zext = dyn_cast<ZExtInst>(_v)) {
		bool didReduce = false;
		if (collectConcatMembersStackConcatMember(zext->getOperand(0), members,
				mainOffset, mainWidth, mainEnd, currentOffset, offsetOfIRes,
				widthOfIRes, didReduce, 0, 2))
			return didReduce;

		size_t paddingWidth = zext->getType()->getIntegerBitWidth()
				- zext->getOperand(0)->getType()->getIntegerBitWidth();
		auto *paddingVal = ConstantInt::get(
				IntegerType::get(zext->getContext(), paddingWidth), 0);
		collectConcatMembersStackConcatMember(paddingVal, members, mainOffset,
				mainWidth, mainEnd, currentOffset, offsetOfIRes, widthOfIRes,
				didReduce, 1, 2);
		return didReduce;

	} else if (auto sext = dyn_cast<SExtInst>(_v)) {
		bool didReduce = false;
		auto sextOp0 = sext->getOperand(0);
		size_t resultWidth = sext->getType()->getIntegerBitWidth();
		size_t paddingWidth = resultWidth
				- sextOp0->getType()->getIntegerBitWidth();
		if (collectConcatMembersStackConcatMember(sextOp0, members, mainOffset,
				mainWidth, mainEnd, currentOffset, offsetOfIRes, widthOfIRes,
				didReduce, 0, 1 + paddingWidth))
			return didReduce;
		IRBuilder<> Builder(sext);
		if (auto sextOpAsInst = dyn_cast<Instruction>(sextOp0)) {
			Builder.SetInsertPoint(sextOpAsInst);
		} else {
			assert(isa<ConstantData>(sextOp0));
			// Builder should not be used
		}
		Value *msb = CreateBitRangeGetConst(&Builder, sextOp0, resultWidth - 1,
				1);
		for (size_t i = 0; i < paddingWidth; ++i) {
			if (collectConcatMembersStackConcatMember(msb, members, mainOffset,
					mainWidth, mainEnd, currentOffset, offsetOfIRes,
					widthOfIRes, didReduce, i + 1, 1 + paddingWidth))
				return didReduce;

		}
		return didReduce;
	}

	return collectConcatMembersAsItIs(_v, members, mainOffset, mainWidth,
			currentOffset, offsetOfIRes, widthOfIRes);
}

llvm::Value* rewriteExtractOnMergeValues(llvm::IRBuilder<> &Builder,
		llvm::Instruction *I) {
	if (isa<TruncInst>(I)) {

	} else {
		auto *CI = dyn_cast<CallInst>(I);
		assert(IsBitRangeGet(CI));
	}
	std::vector<ConcatMember> concatMembers;
	//uint64_t mainOffset = MI.getOperand(2).getImm();
	uint64_t resWidth = I->getType()->getIntegerBitWidth();
	uint64_t currentOffset = 0;
	uint64_t mainOffset = 0;
	bool didReduce = collectConcatMembers(I, concatMembers, mainOffset,
			resWidth, currentOffset, 0, resWidth);
	if (!didReduce)
		return I;
	assert(
			concatMembers.size()
					&& "There must be something which EXTRACT selects");

	IRBuilder<>::InsertPointGuard g(Builder);
	Builder.SetInsertPoint(I->getParent());
	Builder.SetInsertPoint(I->getNextNode());

	Value *newVal = I;
	llvm::SmallVector<Value*> concatArgs;
	for (ConcatMember &src : concatMembers) {
		concatArgs.push_back(
				CreateBitRangeGetConst(&Builder, src.v, src.offsetOfUse,
						src.widthOfUse));
	}
	{
		newVal = CreateBitConcat(&Builder, concatArgs);
		if (newVal != I) {
			I->replaceAllUsesWith(newVal);
			if (I->hasName() && !newVal->hasName())
				newVal->setName(I->getName());
		}
	}
	return newVal;
}

}
