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
				// [todo] check if thisMemberOffset is computed correctly for more than 2 operands
				uint64_t thisMemberOffset = 0;
				uint64_t width = arg->getType()->getIntegerBitWidth();
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
					didReduce |= collectConcatMembers(arg, members, mainOffset,
							mainWidth, currentOffset, thisMemberOffset, width);

				}
				if (currentOffset >= mainEnd) {
					// we do not care about successors because parent EXTRACT does not select them
					didReduce |= argI != CI->arg_size() - 1;
					break;
				}
				++argI;
			}
			return didReduce;
		} else if (IsBitRangeGet(CI)) {
			// e.g. %1 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %1, i5 0)
			auto _subSliceOffset = dyn_cast<ConstantInt>(CI->getArgOperand(1));
			if (_subSliceOffset) {
				uint64_t subSliceOffset = _subSliceOffset->getZExtValue();
				uint64_t subSliceResWidth = CI->getType()->getIntegerBitWidth();
				subSliceOffset += offsetOfIRes;
				if (widthOfIRes > subSliceResWidth) {
					errs() << *CI << " widthOfIRes:" << widthOfIRes << "\n";
					llvm_unreachable(
							"HWTFPGA_EXTRACT provides value of less bits than expected");
				}
				auto *_src = CI->getArgOperand(0);
				if (auto *src = dyn_cast<CallInst>(_src)) {
					// look trough the source operand of this extract instruction
					bool mayContainOtherSlicesAndConcats = IsBitConcat(src)
							|| IsBitRangeGet(src);
					if (mayContainOtherSlicesAndConcats) {
						bool didReduce = collectConcatMembers(src, members,
								mainOffset, mainWidth, currentOffset,
								subSliceOffset, subSliceResWidth);
						assert(members.size());
						auto &lastAdded = members.back();
						didReduce |= lastAdded.v != src;
						return didReduce;
					}
				}
			}
		}
	}
	return collectConcatMembersAsItIs(_v, members, mainOffset, mainWidth,
			currentOffset, offsetOfIRes, widthOfIRes);
}

llvm::Value* rewriteExtractOnMergeValues(llvm::IRBuilder<> &Builder,
		llvm::CallInst *I) {
	assert(IsBitRangeGet(I));
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
