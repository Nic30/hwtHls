#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchSuccessorHoistCode.h>

#include <algorithm>
#include <tuple>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/IteratedDominanceFrontier.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

using InstrIteratorRangeVector = SmallVector<std::pair<BasicBlock::iterator, BasicBlock::iterator>>;

void SkipDebugInfoIfNotIdentical(InstrIteratorRangeVector &InstrIterators) {
	if (InstrIterators[0].first == InstrIterators[0].second)
		return;
	Instruction *I1 = &*InstrIterators[0].first;
	// Skip debug info if it is not identical.
	DbgInfoIntrinsic *DBI1 = dyn_cast<DbgInfoIntrinsic>(I1);
	bool skip = false;
	if (DBI1) {
		auto otherIterators = make_range(InstrIterators.begin() + 1,
				InstrIterators.end());
		// skip if any other is not DbgInfoIntrinsic or is not identical
		skip =
				any_of(otherIterators,
						[&InstrIterators, DBI1](
								std::pair<BasicBlock::iterator,
										BasicBlock::iterator> &Itr) -> bool {
							if (Itr.first == Itr.second)
								return true; // already on the end
							Instruction *I2 = &*Itr.first;
							DbgInfoIntrinsic *DBI2 = dyn_cast<DbgInfoIntrinsic>(
									I2);
							return !DBI2 || !DBI1->isIdenticalTo(DBI2);

						});
	} else {
		skip = true;
	}
	if (skip) {
		for (auto &Itr : InstrIterators) {
			while (isa<DbgInfoIntrinsic>(&*Itr.first))
				Itr.first++;
		}
	}
}

void HoistInstrFromSuccessors(BasicBlock &ParentBlock,
		BasicBlock::iterator ParentTerm,
		InstrIteratorRangeVector &InstrIterators) {
	Instruction *I1 = &*InstrIterators[0].first;
	for (auto &_I2 : InstrIterators) {
		assert(_I2.first != _I2.second);
		Instruction *I2 = &*_I2.first;
		++_I2.first; // move iterator before modifying I2

		if (isa<DbgInfoIntrinsic>(I2)) {
			// The debug location is an integral part of a debug info intrinsic
			// and can't be separated from it or replaced.  Instead of attempting
			// to merge locations, simply hoist both copies of the intrinsic.
			ParentBlock.splice(ParentTerm, I2->getParent(), I1->getIterator());
		} else {
			// For a normal instruction, we just move one to right before the
			// branch, then replace all uses of the other with the first.  Finally,
			// we remove the now redundant second instruction.
			if (I2 == I1) {
				ParentBlock.splice(ParentTerm, I1->getParent(),
						I1->getIterator());
			} else {
				if (!I2->use_empty()) {
					assert(I2->getType() == I1->getType());
					I2->replaceAllUsesWith(I1);
				}
				I1->andIRFlags(I2);
				unsigned KnownIDs[] = { LLVMContext::MD_tbaa,
						LLVMContext::MD_range, LLVMContext::MD_fpmath,
						LLVMContext::MD_invariant_load, LLVMContext::MD_nonnull,
						LLVMContext::MD_invariant_group, LLVMContext::MD_align,
						LLVMContext::MD_dereferenceable,
						LLVMContext::MD_dereferenceable_or_null,
						LLVMContext::MD_mem_parallel_loop_access,
						LLVMContext::MD_access_group,
						LLVMContext::MD_preserve_access_index };
				combineMetadata(I1, I2, KnownIDs, true);

				// I1 and I2 are being combined into a single instruction.  Its debug
				// location is the merged locations of the original instructions.
				I1->applyMergedLocation(I1->getDebugLoc(), I2->getDebugLoc());

				I2->eraseFromParent();
			}
		}
	}
}

enum InstructionCompareResult {
	IDENTICAL, NON_IDENTICAL, END_INSTRUCTION_COMPARING, COMPARABLE_TERMINATORS,
};

InstructionCompareResult checkCompatiblityOfInstructions(Instruction *I1,
		Instruction *I2, unsigned NumSkipped,
		SmallVector<unsigned>::iterator skipFlagsIt,
		const TargetTransformInfo &TTI) {
	assert(I1);
	assert(I2);
	bool isI1 = I1 == I2;
	// If we are hoisting the terminator instruction, don't move one (making a
	// broken BB), instead clone it, and remove BI.
	if (I1->isTerminator() || I2->isTerminator()) {
		// If any instructions remain in the block, we cannot hoist terminators.
		if (NumSkipped || !I1->isIdenticalToWhenDefined(I2))
			return END_INSTRUCTION_COMPARING;
		return COMPARABLE_TERMINATORS;
	}
	if (isa<PHINode>(I2))
		return END_INSTRUCTION_COMPARING;
	if (isI1 || I1->isIdenticalToWhenDefined(I2)) {
		// Even if the instructions are identical, it may not be safe to hoist
		// them if we have skipped over instructions with side effects or their
		// operands weren't hoisted.
		if (!isSafeToHoistInstr(I2, *skipFlagsIt))
			return END_INSTRUCTION_COMPARING;

		// If we're going to hoist a call, make sure that the two instructions
		// we're commoning/hoisting are both marked with musttail, or neither of
		// them is marked as such. Otherwise, we might end up in a situation where
		// we hoist from a block where the terminator is a `ret` to a block where
		// the terminator is a `br`, and `musttail` calls expect to be followed by
		// a return.
		if (!isI1) {
			auto *C1 = dyn_cast<CallInst>(I1);
			auto *C2 = dyn_cast<CallInst>(I2);
			if (C1 && C2)
				if (C1->isMustTailCall() != C2->isMustTailCall())
					return END_INSTRUCTION_COMPARING;

		}
		if (!TTI.isProfitableToHoist(I2))
			return END_INSTRUCTION_COMPARING;

		// If any of the two call sites has nomerge attribute, stop hoisting.
		if (const auto *CB2 = dyn_cast<CallBase>(I2))
			if (CB2->cannotMerge())
				return END_INSTRUCTION_COMPARING;
		if (isa<DbgInfoIntrinsic>(I1) || isa<DbgInfoIntrinsic>(I2)) {
			assert(isa<DbgInfoIntrinsic>(I1) && isa<DbgInfoIntrinsic>(I2));
		}
		// now the _I2 iterator ended up on position where is instruction compatible with I1
		return IDENTICAL;
	} else {
		return NON_IDENTICAL;
	}
}
/// :note: based on SimplifyCFGOpt::HoistThenElseCodeToIf
/// Given a conditional branch that goes to s, hoist any common code
/// in the two blocks up into the branch block. The caller of this function
/// guarantees that BI's block dominates BB1 and BB2. If EqTermsOnly is given,
/// only perform hoisting in case both blocks only contain a terminator. In that
/// case, only the original BI will be replaced and selects for PHIs are added.
bool HoistFromSwitchSuccessors(SwitchInst *SI, const TargetTransformInfo &TTI,
		unsigned HoistCommonSkipLimit) {
	// This does very trivial matching, with limited scanning, to find identical
	// instructions in blocks.  In particular, we don't want to get into
	// O(M*N) situations here where M and N are the sizes of BB1 and BB2.  As
	// such, we currently just scan for obviously identical instructions in an
	// identical order, possibly separated by the same number of non-identical
	// instructions.
	SmallVector<BasicBlock*> Successors;
	InstrIteratorRangeVector InstrIterators;
	auto SucCnt = SI->getNumSuccessors();
	assert(
			SucCnt > 1
					&& "Implemented only for such a case, 0 or 1 is degenerated case which should be handled elsewhere");
	for (size_t SucI = 0; SucI < SucCnt; ++SucI) {
		BasicBlock *Suc = SI->getSuccessor(SucI);
		// If either of the blocks has it's address taken, then we can't do this fold,
		// because the code we'd hoist would no longer run when we jump into the block
		// by it's address.
		if (Suc->hasAddressTaken())
			return false;
		if (std::find(Successors.begin(), Successors.end(), Suc)
				== Successors.end()) {
			Successors.push_back(Suc);
			InstrIterators.push_back( { Suc->begin(), Suc->end() });
		}
	}

	SkipDebugInfoIfNotIdentical(InstrIterators);

	BasicBlock *SIParent = SI->getParent();

	bool Changed = false;

	// Record any skipped instructions that may read memory, write memory or have
	// side effects, or have implicit control flow.
	SmallVector<unsigned> SkipFlags;
	std::fill(SkipFlags.begin(), SkipFlags.end(), 0);

	for (;;) { // cycle to find all compatible instructions
		Instruction *I1 = &*InstrIterators[0].first;
		auto skipFlagsIt = SkipFlags.begin();
		for (auto &_I2 : InstrIterators) { // cycle to check all successor blocks for compatible instrucitons
			//BasicBlock::iterator I2ItInitial = _I2;
			// Count how many instructions were not hoisted so far. There's a limit on how
			// many instructions we skip, serving as a compilation time control as well as
			// preventing excessive increase of life ranges.
			unsigned NumSkipped = 0;
			for (;;) { // cycle to implement instruction search distance
				if (_I2.first == _I2.second)
					return Changed;
				Instruction *I2 = &*_I2.first;
				auto cmpRes = checkCompatiblityOfInstructions(I1, I2,
						NumSkipped, skipFlagsIt, TTI); // intentionally comparing I1 with I1 to check if it can be hoisted
				if (cmpRes == IDENTICAL) {
					break;
				} else if (cmpRes == NON_IDENTICAL) {
					if (NumSkipped >= HoistCommonSkipLimit)
						return Changed;
					// We are about to skip over a pair of non-identical instructions. Record
					// if any have characteristics that would prevent reordering instructions
					// across them.
					*skipFlagsIt |= skippedInstrFlags(I2);
					++NumSkipped;
					++_I2.first;
				} else if (cmpRes == END_INSTRUCTION_COMPARING) {
					return Changed;
				} else {
					assert(cmpRes == COMPARABLE_TERMINATORS);
					goto HoistTerminator;
				}
			}
		}
		// successfully checked all iterators and iterators currently are all on compatible instruction
		HoistInstrFromSuccessors(*SIParent, SI->getIterator(), InstrIterators);
		SkipDebugInfoIfNotIdentical(InstrIterators);

		Changed = true;
	}
	return Changed;
	HoistTerminator: return Changed;

}

}
