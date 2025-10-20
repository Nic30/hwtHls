#pragma once

#include <llvm/ADT/SmallVector.h>
#include <llvm/IR/Metadata.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

namespace hwtHls::MetadataBitRanges {
	/*
	 * Vector of tuples use by multiple metadata to store info about affected bits
     * :note: ranges are in left enclosed format, <0, 2) contains values 0, 1
	 * */
using BitRanges = llvm::SmallVector<std::pair<size_t, size_t>>;

// :param mdNode: input mdNode which is MDTuple of MDTuples with 2 integers (left, right boundary)
void fromMetadata(llvm::MDNode *mdTuple, BitRanges &res);

llvm::MDTuple* rangeMetadataToMetadata(llvm::LLVMContext &Ctx,
		const BitRanges &arr);

// based on https://www.geeksforgeeks.org/dsa/merging-intervals/
// :note: modified so that 1b range overlap is required for intervals to merge
void mergeOverlapedIntervals(BitRanges &arr, BitRanges &res);

void intervalsApplySlice(const BitRanges &arr, size_t offset, size_t width,
		BitRanges &res);
void intervalsApplyOffset(const BitRanges &arr, size_t offset, BitRanges &res);

bool updateRangeMetadata(llvm::Instruction &I, unsigned MDKindID,
		const BitRanges &ranges);

void propagateUseToDefBitwidthReducing(OffsetWidthValue src,
		llvm::Instruction &srcI, unsigned MDKindID, const BitRanges &bitRanges);

void propagateDefToUseBitwidthReducing(OffsetWidthValue uSlice,
		llvm::Instruction &userI, unsigned MDKindID,
		const BitRanges &bitRanges);

// :note: MDKindID = M.getContext().getMDKindID(mdName)
void propagateBiDir(llvm::Instruction &I, unsigned MDKindID,
		const BitRanges &bitRanges);

void setAndPropagateBiDir(llvm::Instruction &I, unsigned MDKindID,
		const BitRanges &bitRanges);

// query the metadata of instruction I and possibly ZExt/SExt/Trunc/hwtHls.bitRangeGet instructions recursively
bool isSelected(llvm::Instruction &I, unsigned MDKindID);
bool isSelected(llvm::Instruction &I, unsigned MDKindID, std::pair<size_t, size_t> range);

}
