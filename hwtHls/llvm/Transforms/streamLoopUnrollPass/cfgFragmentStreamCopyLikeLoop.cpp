#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/cfgFragmentStreamCopyLikeLoop.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/Analysis/SimplifyQuery.h>
#include <llvm/IR/Dominators.h>

#define DEBUG_TYPE "CfgFragmentStreamCopyLikeLoop"
#include <llvm/Transforms/Utils/InstructionWorklist.h>

#include <unordered_set>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

using namespace llvm;

namespace hwtHls {

void precomputeTransitiveUsersOfStreamReadDataInLoop(const Loop &L,
		CallInst &read, std::unordered_set<Instruction*> &usersOfReadData) {
	// precompute reach of data
	auto readDataWidth = streamReadGetOrigChunkBitWidth(&read);
	InstructionWorklist Worklist; // instructions which were just resolved to be dependent
	// and we have to search its users
	for (User *U : read.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (!L.contains(UI))
				continue; // not of interest
			// check if the instruction is not just extract of non-data bits
			if (auto CI = dyn_cast<CallInst>(UI)) {
				if (IsBitRangeGet(CI)) {
					if (BitRangeGetOffset(CI) >= readDataWidth) {
						continue; // does not select the data
					}
				}
			}
			usersOfReadData.insert(UI);
			Worklist.push(UI);
		}
	}
	while (!Worklist.isEmpty()) {
		// Walk deferred instructions in reverse order, and push them to the
		// worklist, which means they'll end up popped from the worklist in-order.
		while (llvm::Instruction *I = Worklist.popDeferred()) {
			Worklist.push(I);
		}

		llvm::Instruction *I = Worklist.removeOne();
		if (I == nullptr)
			continue;  // skip null values.
		for (User *U : I->users()) {
			if (auto UI = dyn_cast<Instruction>(U)) {
				if (!L.contains(UI))
					continue; // not of interest
				if (usersOfReadData.contains(UI))
					continue; // already known to be dependent
				usersOfReadData.insert(UI);
				Worklist.push(UI);
			}
		}
	}
}

bool checkAllSuccessorsInLoopAreDominatedBy(const Loop &L,
		const DominatorTree &DT, BasicBlock &dominatingBB, BasicBlock &curBB,
		std::set<BasicBlock*> &seen) {
	seen.insert(&curBB);
	for (auto suc : successors(&curBB)) {
		if (seen.contains(&curBB))
			continue;

		if (!L.contains(suc))
			continue;

		if (L.getHeader() == suc)
			continue;

		if (!DT.dominates(&dominatingBB, suc))
			return false;

		if (!checkAllSuccessorsInLoopAreDominatedBy(L, DT, dominatingBB, *suc,
				seen))
			return false;
	}
	return true;
}

bool CfgFragmentStreamCopyLikeLoop::isEndingWithEoFCheck(llvm::BasicBlock &BB,
		const StreamChannelFormatInfo &streamInfoForRead, BasicBlock *&exitBB,
		llvm::Value *&rEoF) const {
	auto ter = dyn_cast<BranchInst>(BB.getTerminator());
	if (!ter)
		return false;

	if (ter->getSuccessor(1) != &BB)
		return false; // this is not 1 block loop which we are detecting
	exitBB = ter->getSuccessor(0);

	if (!streamInfoForRead.hasEoF())
		return false;
	rEoF = streamInfoForRead.streamReadFindEoF(read);
	if (!rEoF)
		return false;
	if (ter->getCondition() != rEoF) {
		return false;
	}
	return true;
}

bool CfgFragmentStreamCopyLikeLoop::isExactlyReadUntilEof(
		const StreamChannelFormatInfo &streamInfoForRead,
		BasicBlock *&exitBB) const {
	// detect cases like:
	// .. code-block:: llvm
	//
	//     loop.pkt.drop:                                    ; preds = %loop.pkt.drop.before, %loop.pkt.drop
	//       %rx_read = call i10 @hwtHls.streamRead.p1.i64.i1.i10(ptr addrspace(1) %rx, i64 8, i1 true) #2
	//       %rx_read_eof = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read, i5 9) #3
	//       br i1 %rx_read_eof, label %blockL80i0_832, label %loop.pkt.drop
	if (!read || write)
		return false;

	auto BB = read->getParent();
	if (&*BB->begin() != read)
		return false;
	Value *rEoF;
	if (!isEndingWithEoFCheck(*BB, streamInfoForRead, exitBB, rEoF))
		return false;
	return true;
}

bool CfgFragmentStreamCopyLikeLoop::readUntilEofContainsNoAdditionalInstructions() const {
	assert(read);
	assert(
			std::distance(parentLoop.block_begin(), parentLoop.block_end())
					== 1);
	size_t expectedSize = 1 // read
	+ 1  // eof extract
			+ 1; // terminator
	return read->getParent()->size() == expectedSize;
}

bool CfgFragmentStreamCopyLikeLoop::isExactlyJustCopy(
		const StreamChannelFormatInfo &streamInfoForRead,
		const StreamChannelFormatInfo &streamInfoForWrite,
		BasicBlock *&exitBB) const {
	// detect cases like:
	// .. code-block:: llvm
	//
	//     bb.copyLoop:
	//       %rx_read = call i10 @hwtHls.streamRead.p1.i64.i1.i10(ptr addrspace(1) %rx, i64 8, i1 false) #2
	//       ; the loop contains only hwtHls.streamRead and @hwtHls.streamWrite and
	//       %rx_read_eof = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %rx_read, i5 9) #3
	//       %rx_read_strb = call i1 @hwtHls.bitRangeGet.i10.i5.i1.8(i10 %rx_read, i5 8) #3
	//       %rx_read_data = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %rx_read, i5 0) #3
	//       call void @hwtHls.streamWrite.masked.p2.i8.i1.i1.i1(ptr addrspace(2) %tx, i8 %rx_read_data, i1 %rx_read_strb, i1 false, i1 %rx_read_eof) #2
	//       ; br exits the loop on eof
	//       br i1 %rx_read_eof, label %bb.eof, label %bb.dataLoop
	//
	exitBB = nullptr;
	if (!read || !write)
		return false;

	auto BB = read->getParent();
	if (BB != write->getParent())
		return false;

	if (&*BB->begin() != read)
		return false;
	Value *rEoF;
	if (!isEndingWithEoFCheck(*BB, streamInfoForRead, exitBB, rEoF))
		return false;
	// [todo] maybe extend StreamChannelWordValue so we do not have to extract @hwtHls.streamWrite args manually

	// @hwtHls.streamWrite.masked args: ioArgPtr, valueToWrite, writeMaskOrEmpty, isSoF, isEoF
	// @hwtHls.streamWrite        args: ioArgPtr, valueToWrite,                   isSoF, isEoF
	auto rData = streamInfoForRead.streamReadFindData(read);
	if (streamWriteGetWriteData(write) != rData)
		return false;

	// check that mask/empty is connected directly from read to write
	if (streamInfoForRead.byteEnableEncoding
			!= streamInfoForWrite.byteEnableEncoding)
		return false; // (not implemented conversion between mask/empty)
	switch (streamInfoForRead.byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
	case ByteEnableEncoding::BEE_MASK: {
			auto wMask = streamWriteGetWriteMaskOrEmpty(write);
			if (wMask) {
				Value *rMask = nullptr;
				if (streamInfoForRead.hasMask()) {
					rMask = streamInfoForRead.streamReadFindMask(read);
				}
				if (wMask != rMask
						&& !(rMask == nullptr && isa<ConstantInt>(wMask)
								&& dyn_cast<ConstantInt>(wMask)->getValue().isAllOnes())) {
					return false;
				}
			}
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
			auto wEmpty = streamWriteGetWriteMaskOrEmpty(write);
			if (wEmpty) {
				Value *rEmpty = nullptr;
				if (streamInfoForRead.hasEmpty()) {
					rEmpty = streamInfoForRead.streamReadFindEmpty(read);
				}
				if (wEmpty != rEmpty
						&& !(rEmpty == nullptr && isa<ConstantInt>(wEmpty)
								&& dyn_cast<ConstantInt>(wEmpty)->getValue().isZero())) {
					return false;
				}
			}
		break;
	}
	default:
		llvm_unreachable("Invalid value for byte enable encoding of a stream");
	}

	// check that SoF is connected directly from read to write
	if (streamInfoForWrite.hasSoF()) {
		if (streamInfoForRead.hasSoF()) {
			auto rSoF = streamInfoForRead.streamReadFindSoF(read);
			auto wSoF = streamWriteGetWriteSoF(write);
			if (rSoF != wSoF)
				return false;
		} else {
			return false;
		}
	}

	// check that EoF is connected directly from read to write
	if (streamInfoForWrite.hasEoF()) {
		auto wEoF = streamWriteGetWriteEoF(write);
		if (rEoF != wEoF)
			return false;
	}

	return true;
}

bool CfgFragmentStreamCopyLikeLoop::justCopyContainsOnlyInstructionsForCopy() const {
	assert(read && write);
	assert(
			std::distance(parentLoop.block_begin(), parentLoop.block_end())
					== 1);
	size_t expectedSize = 1  // read
	+ count_if(write->args(), [this](Use &a) {
		return isa<Instruction>(a.get()) && a.get() != read;
	}) + // slices of read data
			+1 // write
			+ 1; // terminator
	return read->getParent()->size() == expectedSize;
}

bool CfgFragmentStreamCopyLikeLoop::blockInstructionsHaveExternalUsers() const {
	assert(
			std::distance(parentLoop.block_begin(), parentLoop.block_end())
					== 1);
	auto &BB = *parentLoop.getHeader();
	for (auto &I : BB) {
		for (auto *U : I.users()) {
			auto UI = dyn_cast<Instruction>(U);
			if (!UI)
				return true;
			if (UI->getParent() != &BB)
				return true;
		}
	}
	return false;

}

std::optional<CfgFragmentStreamCopyLikeLoop> CfgFragmentStreamCopyLikeLoop::detect(
		const llvm::SimplifyQuery &SQ, ScalarEvolution &SE,
		const llvm::Loop &L) {
	CfgFragmentStreamCopyLikeLoop res(L);
	for (BasicBlock *BB : L.blocks()) {
		for (Instruction &I : *BB) {
			auto ci = dyn_cast<CallInst>(&I);
			if (!ci)
				continue;

			if (IsStreamWrite(ci)) {
				if (res.write) {
					// there is more than just a single write
					return {};
				} else {
					res.write = ci;
				}
			} else if (IsStreamRead(ci)) {
				if (res.read) {
					// there is more than just a single read
					return {};
				} else {
					if (res.write) {
						// read does not dominate write
						return {};
					}
					if (BB == L.getHeader()) {
						res.read = ci;
					} else {
						// read is not in the header block
						return {};
					}
				}
			}
		}
	}
	if (!res.read && !res.write)
		return {}; // no write or read in this loop

	if (res.read && res.write && !SQ.DT->dominates(res.read, res.write)) {
		return {}; // because it does not dominate it means that there
		// is some alternative path to write thus we can not reduce this to just copy with
		// some limit condition
	}
	// now we have single read+write or read or write
	if (res.write) {
		// in simple scenario the write is placed in latch
		// or in guarded larch predecessor
		//    bb.guard-\
		//       |      bb.write
		//    bb.latch-/
		// however this CFG pattern may be actually anywhere in the loop

		// thus we first detect the case of guarder bb.write
		// then we check that bb.latch dominates all successors until the end of the loop
		// (until we are in loop L and we did not hit L header)

		// seenBBs is used because there may be child loops dominated by the bb.latch
		// and because we do not want to check successors multiple times on each path trough the code

		// there are several cases which may happen and which we are able to process
		// 1. the write block is only exiting block of the loop
		//    this is typically do
		//    do {
		//     r = read();
		//     write(r);
		//    } while (!r.eof)
		//
		// 2. the predecessor of write bb is only exiting block
		//    this is typically
		//    while(1) {
		//     r = read();
		//     if (filter(r)) break;
		//     write(r);
		//    }
		//
		// 3. the write bb and its predecessor are only exiting block
		//    this is typically
		//    do {
		//     r = read();
		//     if (filter(r)) break;
		//     write(r);
		//    } while (!r.eof)
		//
		// :note: the read is optional, if it is not present the r.eof check
		//        may be any other expression

		// try detect block guard
		auto &wrBB = *res.write->getParent();
		res.writeGuardBB = wrBB.getUniquePredecessor();
		if (res.writeGuardBB) {
			auto guardBBTerm = dyn_cast<BranchInst>(
					res.writeGuardBB->getTerminator());
			if (!guardBBTerm || guardBBTerm->getNumSuccessors() != 2) {
				// we detect the case only with a single bb.latch for now
				return {};
			}
			res.writeEnableCondition = guardBBTerm->getCondition();
			if (guardBBTerm->getSuccessor(0) == &wrBB) {
				res.writeLatchBB = guardBBTerm->getSuccessor(1);
			} else {
				assert(guardBBTerm->getSuccessor(1) == &wrBB);
				res.writeLatchBB = guardBBTerm->getSuccessor(0);
				res.writeEnableConditionIsNegated = true;
			}
		} else {
			res.writeLatchBB = &wrBB;
		}
		std::set<BasicBlock*> seen;
		if (!checkAllSuccessorsInLoopAreDominatedBy(L, *SQ.DT,
				*res.writeLatchBB, *res.writeLatchBB, seen)) {
			return {};
		}
	}
	// now we know that we are able to resolve the write condition

	if (res.read) {
		// check that each exit condition from loop does not depend on on read data
		std::unordered_set<Instruction*> usersOfReadData;
		precomputeTransitiveUsersOfStreamReadDataInLoop(L, *res.read,
				usersOfReadData);
		// :note: write enable is allowed to be driven from read data
		//    because we extract read before unrolled section, and write after it
		//    so the data will be available for write, but not for the read itself
		SmallVector<BasicBlock*> exitingBlocks;
		L.getExitingBlocks(exitingBlocks);
		for (auto *exitingBB : exitingBlocks) {
			auto ter = exitingBB->getTerminator();
			for (auto &op : ter->operands()) {
				if (auto opI = dyn_cast<Instruction>(op.get())) {
					if (usersOfReadData.contains(opI)) {
						return {}; // exit condition depends no data
						// thus read can not be extracted as a single instruction
					}
				}
			}
		}
	}
	// from now we know that every exit condition is compatible
	if (res.read && res.writeEnableCondition) {
		// this patten detects only cases which are copy like,
		// with the support for limiting condition of the copy
		// this is because we wan to cover the case like copy n-bytes from rx
		// to tx and drop the rest
		// SE.getConstantMaxBackedgeTakenCount(&L);
		llvm_unreachable(
				"[todo] use SE to prove that once the writeEnableCondition==0 it stays 0 until all iterations of the loop,"
						" This is required because we must assert that there are no holes in output stream data");

	}
	//if (res.read) {
	//	// [todo] use isImpliedConditionAndOrTree to check hat eof implies break from the loop
	//	// isImpliedConditionAndOrTree(Builder, rxEoF, cond,
	//	// 		SQ.DL, SQ.AC, SQ.DT, terminatorOfExitingBB);
	//	// check eof condition implies loop exit condition
	//	auto *headerBB = L.getHeader();
	//	// extract the eof condition from the read call, e.g. rxEoF
	//	Value *rxEoF = IsSt(res.read);
	//
	//	// get the exiting block and its terminator condition
	//	BasicBlock *exitingBB = L.getExitingBlock();
	//	if (!exitingBB)
	//		return {};
	//
	//	auto *terminator = exitingBB->getTerminator();
	//	if (!terminator)
	//		return {};
	//
	//	// get the loop exit condition from terminator branch
	//	Value *cond = nullptr;
	//	if (auto *brInst = dyn_cast<BranchInst>(terminator)) {
	//		if (brInst->isConditional()) {
	//			cond = brInst->getCondition();
	//		}
	//	}
	//	if (!cond)
	//		return {};
	//
	//	// Use analysis utility to verify the logical implication
	//	if (!isImpliedConditionAndOrTree(/*Builder*/nullptr, rxEoF, cond, SQ.DL,
	//			SQ.AC, SQ.DT, terminator)) {
	//		return {};
	//	}
	//}
	return res;
}

}
