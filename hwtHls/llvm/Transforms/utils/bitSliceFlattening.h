#pragma once
#include <llvm/IR/Value.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

struct ConcatMember {
	llvm::Value *v;
	uint64_t offsetOfUse; // bitIndex for first bit in result slice
	uint64_t width; // width of "v"
	uint64_t widthOfUse; // width of result slice
};

/*
 * Recursively collect members of concatenations, looks through HWTFPGA_EXTRACT and HWTFPGA_MERGE_VALUES instructions
 *
 * :param MIOp: an operand from where to collect concat members
 * :param members: output vector of records containing the operand and the information about which bits are selected
 * :param mainOffset: offsets (number of bits) where selected value from whole value
 * :param mainWidth: number of bits to select in total
 * :param currentOffset: a number of bits already collected
 * :param offsetOfIRes: offsets (number of bits) where selected value from this operand starts
 * :param widthOfIRes: a number of bits to select from this operand
 * */
bool collectConcatMembers(llvm::Value *_MI, std::vector<ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &currentOffset,
		uint64_t offsetOfIRes, uint64_t widthOfIRes);

/*
 * Recursively rewrite BitRangeGet and Concat expression to concatenation of slices (if required)
 * :note: value of I is replaced and new replacement is returned
 **/
llvm::Value* rewriteExtractOnMergeValues(llvm::IRBuilder<> &Builder,
		llvm::Instruction *I);
}
