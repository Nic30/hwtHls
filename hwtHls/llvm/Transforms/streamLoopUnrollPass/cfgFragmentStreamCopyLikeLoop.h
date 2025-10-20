#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/LoopInfo.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>

namespace llvm {
class SimplifyQuery;
}

namespace hwtHls {
/*
 * This pass detect stream copy like like behavior.
 * Typically it detect read, write while not read.eof loop.
 * But it also accepts the cases with just read/write.
 * :note: The case without read/write follows the same unrollig rule
 *        that is why it is detected by this fragment as well.
 *
 * .. code-block:: text
 *    :caption: Detected cfg patterns
 *
 *       +->bb.head         +->bb.head       +->bb.head             +->bb.head               +->bb.head
 *       |     |            |     |    \     |     |    \           |     |                  |     |
 *       +--bb.latch        |  bb.write |    |  bb.write bb.exit    |    ...                 |    ...
 *                          |     |    /     |     |                |     |                  |     |
 *                          +--bb.latch      +--bb.latch            |  bb.write.guard        |  bb.write.guard
 *                                                                  |     |    \             |     |     \
 *                                                                  |  bb.write |            |  bb.write  bb.exit
 *                                                                  |     |    /             |     |
 *                                                                  +--bb.latch              +--bb.latch
 *
 * The read may appear only in bb.head.
 * The write may appear only in bb.head/bb.latch or bb.write.
 * The loop may have the exit and if this is the case the
 *
 * .. code-block:: llvm
 *    :caption: Example code which will be detected as this cfg fragment
 *
 *        bb.head:                                      ; preds = %bb.latch, %bb.sof
 *          %rx_read1 = call i10 @hwtHls.streamRead.p1.i64.i1.i10(ptr addrspace(1) %rx, i64 8, i1 false) #2
 *          ; :note: no other access to %rx in whole loop
 *          %rx_read_eof = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read1, i5 9) #3
 *          %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read1, i5 0) #3
 *          %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read1, i5 8) #3
 *          call void @hwtHls.streamWrite.p2.i8.i1.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 false, i1 %rx_read_eof) #2
 *          br i1 %rx_read_eof, label %bb.exit, label %bb.latch
 *
 *        bb.latch:                            ; preds = %bb.head
 *          br i1 %rx_read_eof, label %bb.eof, label %bb.dataLoop, !llvm.loop !5
 *
 */

class CfgFragmentStreamCopyLikeLoop {
public:

	// :attention: read and write are optional but at leas one of them must be set
	//   loop with read and write is copy,
	//   loop with just read is consuming of stream data,
	//   loop with just write is producing of stream data
	const llvm::Loop &parentLoop;
	llvm::CallInst *read;
	llvm::CallInst *write;
	llvm::BasicBlock *writeGuardBB; // blocks for the case that the write is enclosed in "if-then"
	llvm::BasicBlock *writeLatchBB;

	llvm::Value *writeEnableCondition; // in the case that the write is unconditional this is set to nullptr
	bool writeEnableConditionIsNegated;

	CfgFragmentStreamCopyLikeLoop(const llvm::Loop &L) :
			parentLoop(L), read(nullptr), //
			write(nullptr), //
			writeGuardBB(nullptr), //
			writeLatchBB(nullptr), //
			writeEnableCondition(nullptr), //
			writeEnableConditionIsNegated(false) {
	}
	bool isEndingWithEoFCheck(llvm::BasicBlock &BB,
			const StreamChannelFormatInfo &streamInfoForRead,
			llvm::BasicBlock *&exitBB, llvm::Value *&rEoF) const;
	// check that this is just loop which reads from stream until eof
	bool isExactlyReadUntilEof(const StreamChannelFormatInfo &streamInfoForRead,
			llvm::BasicBlock *&exitBB) const;
	bool readUntilEofContainsNoAdditionalInstructions() const;
	// check that this is just-copy loop containing only a single block and copy until eof
	bool isExactlyJustCopy(const StreamChannelFormatInfo &streamInfoForRead,
			const StreamChannelFormatInfo &streamInfoForWrite,
			llvm::BasicBlock *&exitBB) const;
	// check that just-copy loop do not have any additional instruction
	bool justCopyContainsOnlyInstructionsForCopy() const;
	// check that all uses of all instructions in header block of just-copy loop do not have any use outside of this block
	bool blockInstructionsHaveExternalUsers() const;
	static std::optional<CfgFragmentStreamCopyLikeLoop> detect(
			const llvm::SimplifyQuery &SQ, llvm::ScalarEvolution &SE,
			const llvm::Loop &L);
};

}
