#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentOptionaStreamWrite.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/ValueTracking.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

using namespace llvm;

namespace hwtHls {

OptionalStreamWriteCFGFragment::OptionalStreamWriteCFGFragment() :
		guard(nullptr), write(nullptr), exit(nullptr) {
}
OptionalStreamWriteCFGFragment::OptionalStreamWriteCFGFragment(
		llvm::BasicBlock *guard, llvm::CallInst *write, llvm::BasicBlock *exit) :
		guard(guard), write(write), exit(exit) {
}

std::optional<OptionalStreamWriteCFGFragment> OptionalStreamWriteCFGFragment::detect(
		CallInst & write) {
	BasicBlock &writeBB = *write.getParent();
	OptionalStreamWriteCFGFragment res;
	res.write = &write;
	auto ioArg = streamWriteGetIoArg(&write);
#ifndef NDEBUG
	for (auto &I : writeBB) {
		if (&I == &write)
			continue;
		if (auto *CI = dyn_cast<CallInst>(&I)) {
			if (IsStreamWrite(CI) && streamWriteGetIoArg(CI) == ioArg) {
				llvm_unreachable("Consecutive writes in the same block should be already merged before detection of this pattern");
			}
		}
	}
#endif

	res.guard = writeBB.getSinglePredecessor();
	if (!res.guard)
		return {};

	auto wTerm = writeBB.getTerminator();
	if (wTerm->getNumSuccessors() != 1)
		return {};

	res.exit = wTerm->getSuccessor(0);
	if (!res.exit->hasNPredecessors(2))
		return {};

	auto guardTerm = res.guard->getTerminator();
	if (guardTerm->getNumSuccessors() != 2)
		return {};

	for (auto *GuardSuc : successors(res.guard)) {
		if (GuardSuc == &writeBB || GuardSuc == res.exit)
			continue;
		else
			return {};
	}

	return res;
}

bool OptionalStreamWriteCFGFragment::_blockContainsOnlyWriteAndAssumeAndTerminator(
		BasicBlock &BB) const {
	for (auto &I : BB) {
		if (auto II = dyn_cast<IntrinsicInst>(&I)) {
			if (!II->isAssumeLikeIntrinsic())
				return false;
		} else if ((&I != write && !I.isTerminator() && !isSafeToSpeculativelyExecute(&I)) || isa<PHINode>(&I)) {
			return false;
		}
	}
	return true;
}

bool OptionalStreamWriteCFGFragment::containsOnlyStreamWrite(
		bool allowNonEmptyGuard) const {
	if (!allowNonEmptyGuard && guard->size() != 1) {
		return _blockContainsOnlyWriteAndAssumeAndTerminator(*guard);
	}
	if (write->getParent()->size() != 2)
		return _blockContainsOnlyWriteAndAssumeAndTerminator(
				*write->getParent());
	if (exit->size() != 1)
		return _blockContainsOnlyWriteAndAssumeAndTerminator(*exit);;

	return true;
}

std::pair<Value*, bool> OptionalStreamWriteCFGFragment::getWriteEnableCondition() const {
	if (!guard)
		return {ConstantInt::getBool(write->getContext(), 1), false};

	auto gTerm = dyn_cast<BranchInst>(guard->getTerminator());
	assert(gTerm);
	bool isNegated = gTerm->getSuccessor(0) != write->getParent();
	if (isNegated)
		assert(gTerm->getSuccessor(1) == write->getParent());

	return {dyn_cast<BranchInst>(gTerm)->getCondition(), isNegated};
}

}
