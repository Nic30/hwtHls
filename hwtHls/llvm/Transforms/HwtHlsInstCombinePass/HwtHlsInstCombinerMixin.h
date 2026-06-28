#pragma once
// :attention: define DEBUG_TYPE_SHORT and DEBUG_TYPE before including this file
#ifndef DEBUG_TYPE
#error "DEBUG_TYPE must be defined"
#endif
#ifndef DEBUG_TYPE_SHORT
#error "DEBUG_TYPE_SHORT must be defined"
#endif


#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/TargetFolder.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/Analysis/SimplifyQuery.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Metadata.h>
#include <llvm/IR/Dominators.h>
#include <llvm/ADT/STLExtras.h>

// :attention: this expects DEBUG_TYPE to be defined
#include <llvm/Transforms/Utils/InstructionWorklist.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/Support/DebugCounter.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/AliasScopeTracker.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/intrinsic/metadataWithBitrange.h>

// :note: for metadata names
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinePass.h>
#include <hwtHls/llvm/Transforms/slicesToIndependentVariablesPass/slicesToIndependentVariablesPass.h>


namespace hwtHls {

// :note: curiously recurring template pattern (CRTP) idiom/ F-bound polymorphism
//        it is used to avoid performance loss due to use of virtual methods which would be required otherwise
template<typename DerivedT>
class HwtHlsInstCombinerMixin {
public:
	using BuilderTy = llvm::IRBuilder<llvm::TargetFolder, llvm::IRBuilderCallbackInserter>;
	bool MadeIRChange;
	llvm::InstructionWorklist &Worklist;
	BuilderTy &Builder;
	const llvm::TargetLibraryInfo &TLI;
	const llvm::DominatorTree &DT;
	const llvm::DataLayout &DL;
	llvm::AssumptionCache &AC;
	llvm::SimplifyQuery SQ;
	llvm::Function &F;

	llvm::Statistic &NumCombined; // Number of insts combined
	llvm::Statistic &NumConstProp; // Number of constant folds
	llvm::Statistic &NumDeadInst; // Number of dead inst eliminated
	const unsigned VisitCounter; // Controls which instructions are visited (the value is an ID of counter)

	/// Edges that are known to never be taken.
	llvm::SmallDenseSet<std::pair<llvm::BasicBlock*, llvm::BasicBlock*>, 8> DeadEdges;
	const char * lastOptRuleName = nullptr;
	using IrChangeCallbackFn = std::function<void(const std::string & ruleName, const llvm::Function & F)>;
	IrChangeCallbackFn* _dbgIrInstrCombineChangeCallbackFn;
	void onChangeCallback(const std::string & ruleName, llvm::Function & F) {
		if (_dbgIrInstrCombineChangeCallbackFn) {
			(*_dbgIrInstrCombineChangeCallbackFn)(ruleName, F);
		}
	}

	HwtHlsInstCombinerMixin(BuilderTy &Builder, llvm::SimplifyQuery SQ,
			llvm::InstructionWorklist &Worklist, llvm::Function &F,
			llvm::Statistic &NumCombined, llvm::Statistic &NumConstProp,
			llvm::Statistic &NumDeadInst, const unsigned VisitCounter,
			IrChangeCallbackFn* _dbgIrInstrCombineChangeCallbackFn=nullptr) :
			MadeIRChange(false), Worklist(Worklist), Builder(Builder), TLI(
					*SQ.TLI), DT(*SQ.DT), DL(SQ.DL), AC(*SQ.AC), SQ(SQ), F(F), NumCombined(
					NumCombined), NumConstProp(NumConstProp), NumDeadInst(
					NumDeadInst), VisitCounter(VisitCounter), lastOptRuleName(nullptr),
					_dbgIrInstrCombineChangeCallbackFn(_dbgIrInstrCombineChangeCallbackFn) {
		assert(SQ.DT && "DominatorTree is required for prepareWorklist() to filter out dead blocks");
		assert(SQ.TLI && "TLI is required for checking if instruction is dead");
	}

	bool prepareWorklist(
			llvm::ReversePostOrderTraversal<llvm::BasicBlock*> &RPOT);
	llvm::Instruction* eraseInstFromFunction(llvm::Instruction &I);
	void eraseInstrRecursivelyIfTriviallyDead(llvm::Value &V);
	llvm::Instruction* replaceInstUsesWith(llvm::Instruction &I, llvm::Value *V,
			bool excludeAssumeUsers = false);
	void inheritAndPropagateBitMetadata(llvm::Instruction &IOld, llvm::Instruction &INew);
	// method called at the beginning of replaceInstUsesWith, it can be used to implement hooks for before instruction remove
	void replaceInstUsesWithBefore(llvm::Instruction &I, llvm::Value *V,
			bool excludeAssumeUsers) {
	}
	llvm::Instruction* replaceOperand(llvm::Instruction &I, unsigned OpNum,
			llvm::Value *V);
	bool run();
	// this method can be used to call other optimization once worklist is empty
	// :returns: true if worklist now contains any instruction
	bool runOptimizationsAfterWorklistEmpty() {
		return false;
	}

};

// copied llvm-21.1.2  llvm::InstCombinerImpl::prepareWorklist
template<typename DerivedT>
bool HwtHlsInstCombinerMixin<DerivedT>::prepareWorklist(
		llvm::ReversePostOrderTraversal<llvm::BasicBlock*> &RPOT) {
	// clean worklist because prepareWorklist may erase unused instructions
	// which would result in deleted item being inside of worklist
	while (Worklist.popDeferred())
		;
	while (Worklist.removeOne())
		;
	Worklist.zap();
	bool MadeIRChange = false;
	llvm::SmallPtrSet<llvm::BasicBlock*, 32> LiveBlocks;
	llvm::SmallVector<llvm::Instruction*, 128> InstrsForInstructionWorklist;
	llvm::DenseMap<llvm::Constant*, llvm::Constant*> FoldedConstants;
	AliasScopeTracker SeenAliasScopes;

	auto HandleOnlyLiveSuccessor = [&](llvm::BasicBlock *BB,
			llvm::BasicBlock *LiveSucc) {
		for (llvm::BasicBlock *Succ : successors(BB))
			if (Succ != LiveSucc && DeadEdges.insert( { BB, Succ }).second)
				for (llvm::PHINode &PN : Succ->phis())
					for (llvm::Use &U : PN.incoming_values())
						if (PN.getIncomingBlock(U) == BB
								&& !isa<llvm::PoisonValue>(U)) {
							U.set(llvm::PoisonValue::get(PN.getType()));
							MadeIRChange = true;
						}
	};
	for (llvm::BasicBlock *BB : RPOT) {
		assert(BB->getParent() == &F && "Check that the block was not removed");
		if (!BB->isEntryBlock()
				&& all_of(predecessors(BB),
						[&](llvm::BasicBlock *Pred) {
							return DeadEdges.contains( { Pred, BB })
									|| DT.dominates(BB, Pred);
						})) {
			HandleOnlyLiveSuccessor(BB, nullptr);
			continue;
		}
		LiveBlocks.insert(BB);

		for (llvm::Instruction &Inst : llvm::make_early_inc_range(*BB)) {
			// ConstantProp instruction if trivially constant.
			if (!Inst.use_empty()
					&& (Inst.getNumOperands() == 0
							|| llvm::isa<llvm::Constant>(Inst.getOperand(0))))
				if (llvm::Constant *C = ConstantFoldInstruction(&Inst, DL,
						&TLI)) {
					LLVM_DEBUG(
							llvm::dbgs() << DEBUG_TYPE_SHORT ": ConstFold to: " << *C << " from: " << Inst << '\n');
					replaceInstUsesWith(Inst, C);
					++NumConstProp;
					if (llvm::isInstructionTriviallyDead(&Inst, &TLI)) {
						static_cast<DerivedT*>(this)->eraseInstFromFunction(Inst);
					}
					MadeIRChange = true;
					continue;
				}

			// See if we can constant fold its operands.
			for (llvm::Use &U : Inst.operands()) {
				if (!llvm::isa<llvm::ConstantVector>(U)
						&& !llvm::isa<llvm::ConstantExpr>(U))
					continue;

				auto *C = llvm::cast<llvm::Constant>(U);
				llvm::Constant *&FoldRes = FoldedConstants[C];
				if (!FoldRes)
					FoldRes = llvm::ConstantFoldConstant(C, DL, &TLI);

				if (FoldRes != C) {
					LLVM_DEBUG(
							llvm::dbgs() << DEBUG_TYPE_SHORT ": ConstFold operand of: " << Inst << "\n    Old = " << *C << "\n    New = " << *FoldRes << '\n');
					U = FoldRes;
					MadeIRChange = true;
				}
			}

			// Skip processing debug and pseudo intrinsics in InstCombine. Processing
			// these call instructions consumes non-trivial amount of time and
			// provides no value for the optimization.
			if (!Inst.isDebugOrPseudoInst()) {
				InstrsForInstructionWorklist.push_back(&Inst);
				SeenAliasScopes.analyse(&Inst);
			}
		}

		// If this is a branch or switch on a constant, mark only the single
		// live successor. Otherwise assume all successors are live.
		llvm::Instruction *TI = BB->getTerminator();
		if (llvm::BranchInst *BI = llvm::dyn_cast<llvm::BranchInst>(TI); BI
				&& BI->isConditional()) {
			if (llvm::isa<llvm::UndefValue>(BI->getCondition())) {
				// Branch on undef is UB.
				HandleOnlyLiveSuccessor(BB, nullptr);
				continue;
			}
			if (auto *Cond = llvm::dyn_cast<llvm::ConstantInt>(
					BI->getCondition())) {
				bool CondVal = Cond->getZExtValue();
				HandleOnlyLiveSuccessor(BB, BI->getSuccessor(!CondVal));
				continue;
			}
		} else if (llvm::SwitchInst *SI = llvm::dyn_cast<llvm::SwitchInst>(
				TI)) {
			if (isa<llvm::UndefValue>(SI->getCondition())) {
				// Switch on undef is UB.
				HandleOnlyLiveSuccessor(BB, nullptr);
				continue;
			}
			if (auto *Cond = llvm::dyn_cast<llvm::ConstantInt>(
					SI->getCondition())) {
				HandleOnlyLiveSuccessor(BB,
						SI->findCaseValue(Cond)->getCaseSuccessor());
				continue;
			}
		}
	}
	// Remove instructions inside unreachable blocks. This prevents the
	// instcombine code from having to deal with some bad special cases, and
	// reduces use counts of instructions.
	for (llvm::BasicBlock &BB : F) {
		if (LiveBlocks.count(&BB))
			continue;
		for (auto &I: BB) {
			Worklist.remove(&I);
		}
		unsigned NumDeadInstInBB;
		NumDeadInstInBB = removeAllNonTerminatorAndEHPadInstructions(&BB);

		MadeIRChange |= NumDeadInstInBB != 0;
		NumDeadInst += NumDeadInstInBB;
	}

	// Once we've found all of the instructions to add to instcombine's worklist,
	// add them in reverse order.  This way instcombine will visit from the top
	// of the function down.  This jives well with the way that it adds all uses
	// of instructions to the worklist after doing a transformation, thus avoiding
	// some N^2 behavior in pathological cases.
	Worklist.reserve(InstrsForInstructionWorklist.size());
	for (llvm::Instruction *Inst : llvm::reverse(InstrsForInstructionWorklist)) {
		// DCE instruction if trivially dead. As we iterate in reverse program
		// order here, we will clean up whole chains of dead instructions.
		if (isInstructionTriviallyDead(Inst, &TLI)
				|| SeenAliasScopes.isNoAliasScopeDeclDead(Inst)) {
			++NumDeadInst;
			LLVM_DEBUG(
					llvm::dbgs() << DEBUG_TYPE_SHORT ": DCE: " << *Inst << '\n');
			salvageDebugInfo(*Inst);
			Worklist.remove(Inst);
			Inst->eraseFromParent();
			MadeIRChange = true;
			continue;
		}
		assert(Inst->getParent()->getParent() == &F && "Check that instruction was not already removed without notifying worklist");
		Worklist.push(Inst);
	}

	return MadeIRChange;
}

template<typename DerivedT>
void HwtHlsInstCombinerMixin<DerivedT>::inheritAndPropagateBitMetadata(
		llvm::Instruction &IOld, llvm::Instruction &INew) {
	auto &ctx = F.getContext();
	auto NoSplitMDKind = ctx.getMDKindID(
			SlicesToIndependentVariablesPass::metadataName_NoSplit);
	auto ContinuousMaskMDKind = ctx.getMDKindID(
			HwtHlsInstCombinePass::metadataName_expr_maskContinuosFromLsb);
	for (auto mdKindId: {NoSplitMDKind, ContinuousMaskMDKind}) {
		auto md = IOld.getMetadata(mdKindId);
		if (!md)
			continue;
		MetadataBitRanges::BitRanges br;
		MetadataBitRanges::fromMetadata(md, br);
		MetadataBitRanges::propagateBiDir(INew, mdKindId, br);
	}
}

// copied copied llvm-18 InstCombiner::replaceInstUsesWith
/// A combiner-aware RAUW-like routine.
///
/// This method is to be used when an instruction is found to be dead,
/// replaceable with another preexisting expression. Here we add all uses of
/// I to the worklist, replace all uses of I with the new value, then return
/// I, so that the inst combiner will know that I was modified.
template<typename DerivedT>
llvm::Instruction* HwtHlsInstCombinerMixin<DerivedT>::replaceInstUsesWith(
		llvm::Instruction &I, llvm::Value *V, bool excludeAssumeUsers) {
#ifndef NDEBUG
	assert(I.getParent() && "Check that old instruction was not yet removed");
	assert(&I != V);
	if (auto* VI = llvm::dyn_cast<llvm::Instruction>(V)) {
		assert(VI->getParent() && "Check that new instruction was not already removed");
	}
#endif
	// If there are no uses to replace, then we return nullptr to indicate that
	// no changes were made to the program.
	if (I.use_empty())
		return nullptr;

	static_cast<DerivedT*>(this)->replaceInstUsesWithBefore(I, V,
			excludeAssumeUsers);
	Worklist.pushUsersToWorkList(I); // Add all modified instrs to worklist.

	// If we are replacing the instruction with itself, this must be in a
	// segment of unreachable code, so just clobber the instruction.
	if (&I == V)
		V = llvm::PoisonValue::get(I.getType());

	LLVM_DEBUG(
			llvm::dbgs() << DEBUG_TYPE_SHORT": Replacing " << I << "\n" << "    with " << *V << '\n');

	// If V is a new unnamed instruction, take the name from the old one.
	if (V->use_empty() && llvm::isa<llvm::Instruction>(V) && !V->hasName()
			&& I.hasName())
		V->takeName(&I);
	if (excludeAssumeUsers) {
		size_t replacedCnt = 0;
		I.replaceUsesWithIf(V, [&replacedCnt](const llvm::Use &U) {
			if (!llvm::isa<llvm::AssumeInst>(U.getUser())) {
				replacedCnt++;
				return true;
			}
			return false;
		});
		if (!replacedCnt) {
			Worklist.addValue(V); // V is potentially unused
			return nullptr;
		}
	} else {
//#ifndef NDEBUG
//		if (llvm::isa<llvm::ConstantInt>(V)) {
//			for (auto *U : I.users()) {
//				assert(
//						!isa<llvm::AssumeInst>(U) &&
//						"Likely the result of simplification of assume using assume itself");
//			}
//		}
//#endif
		I.replaceAllUsesWith(V);
	}
	if (auto VI = llvm::dyn_cast<llvm::Instruction>(V))
		inheritAndPropagateBitMetadata(I, *VI);

	return &I;
}

// copied copied llvm-18 InstCombinerImpl::replaceOperand
/// Replace operand of instruction and add old operand to the worklist.
template<typename DerivedT>
llvm::Instruction* HwtHlsInstCombinerMixin<DerivedT>::replaceOperand(
		llvm::Instruction &I, unsigned OpNum, llvm::Value *V) {
	llvm::Value *OldOp = I.getOperand(OpNum);
	I.setOperand(OpNum, V);
	Worklist.handleUseCountDecrement(OldOp);
	return &I;
}

// copied copied llvm-18 InstCombinerImpl::eraseInstFromFunction
template<typename DerivedT>
llvm::Instruction* HwtHlsInstCombinerMixin<DerivedT>::eraseInstFromFunction(
		llvm::Instruction &I) {
	assert(I.getParent() && "Check that instruction was not already removed without notifying worklist");
	LLVM_DEBUG(llvm::dbgs() << DEBUG_TYPE_SHORT ": ERASE " << I << '\n');
	assert(I.use_empty() && "Cannot erase instruction that is used!");
	llvm::salvageDebugInfo(I);

	// Make sure that we reprocess all operands now that we reduced their
	// use counts.
	llvm::SmallVector<llvm::Value*> Ops(I.operands());
	Worklist.remove(&I);
	// DC.removeValue(&I);
	I.eraseFromParent();
	for (llvm::Value *Op : Ops)
		Worklist.handleUseCountDecrement(Op);
	MadeIRChange = true;
	return nullptr; // Don't do anything with I
}

template<typename DerivedT>
void HwtHlsInstCombinerMixin<DerivedT>::eraseInstrRecursivelyIfTriviallyDead(
		llvm::Value &V) {
	if (auto I = llvm::dyn_cast<llvm::Instruction>(&V)) {
		if (llvm::isInstructionTriviallyDead(I, &TLI)) {
			llvm::SmallVector<llvm::Value*> Ops(I->operands());
			static_cast<DerivedT*>(this)->eraseInstFromFunction(*I);
			++NumDeadInst;
			for (auto O : Ops) {
				eraseInstrRecursivelyIfTriviallyDead(*O);
			}
		}
	}
}

template<typename DerivedT>
bool HwtHlsInstCombinerMixin<DerivedT>::run() {
	while (!Worklist.isEmpty()
			|| static_cast<DerivedT*>(this)->runOptimizationsAfterWorklistEmpty()) {
		// Walk deferred instructions in reverse order, and push them to the
		// worklist, which means they'll end up popped from the worklist in-order.
		while (llvm::Instruction *I = Worklist.popDeferred()) {
			assert(I->getParent() && "Check that instruction was not already removed without notifying worklist");
			// Check to see if we can DCE the instruction. We do this already here to
			// reduce the number of uses and thus allow other folds to trigger.
			// Note that eraseInstFromFunction() may push additional instructions on
			// the deferred worklist, so this will DCE whole instruction chains.
			if (llvm::isInstructionTriviallyDead(I, &TLI)) {
				static_cast<DerivedT*>(this)->eraseInstFromFunction(*I);
				++NumDeadInst;
				continue;
			}

			Worklist.push(I);
		}

		llvm::Instruction *I = Worklist.removeOne();
		if (I == nullptr)
			continue;  // skip null values.
		assert(I->getParent() && "Check that instruction was not already removed without notifying worklist");

		// Check to see if we can DCE the instruction.
		if (llvm::isInstructionTriviallyDead(I, &TLI)) {
			static_cast<DerivedT*>(this)->eraseInstFromFunction(*I);
			++NumDeadInst;
			continue;
		}

		if (!llvm::DebugCounter::shouldExecute(VisitCounter))
			continue;

		// Now that we have an instruction, try combining it to simplify it.
		Builder.SetInsertPoint(I);
		Builder.CollectMetadataToCopy(I, { llvm::LLVMContext::MD_dbg,
				llvm::LLVMContext::MD_annotation });

#ifndef NDEBUG
		std::string OrigI;
#endif
		LLVM_DEBUG(
				llvm::raw_string_ostream SS(OrigI); I->print(SS); OrigI = SS.str(););
		LLVM_DEBUG(
				llvm::dbgs() << DEBUG_TYPE_SHORT ": Visiting: " << OrigI << '\n');

		if (llvm::Instruction *Result =
				static_cast<DerivedT*>(this)->runOnInstr(*I)) {
			++NumCombined;
			// Should we replace the old instruction with a new one?
			if (Result != I) {
				LLVM_DEBUG(
						llvm::dbgs() << DEBUG_TYPE_SHORT ": Old = " << *I << '\n' << "    New = " << *Result << '\n');

		        // We copy the old instruction's DebugLoc to the new instruction, unless
		        // InstCombine already assigned a DebugLoc to it, in which case we
		        // should trust the more specifically selected DebugLoc.
		        Result->setDebugLoc(Result->getDebugLoc().orElse(I->getDebugLoc()));
		        // We also copy annotation metadata to the new instruction.
		        Result->copyMetadata(*I, llvm::LLVMContext::MD_annotation);
				// Everything uses the new instruction now.
				I->replaceAllUsesWith(Result);

				// Move the name to the new instruction first.
				Result->takeName(I);

				// Insert the new instruction into the basic block...
				llvm::BasicBlock *InstParent = I->getParent();
				llvm::BasicBlock::iterator InsertPos = I->getIterator();

				// Are we replace a PHI with something that isn't a PHI, or vice versa?
				if (llvm::isa<llvm::PHINode>(Result)
						!= llvm::isa<llvm::PHINode>(I)) {
					// We need to fix up the insertion point.
					if (llvm::isa<llvm::PHINode>(I)) { // PHI -> Non-PHI
						InsertPos = InstParent->getFirstInsertionPt();
					} else {
						// Non-PHI -> PHI
						InsertPos = InstParent->getFirstNonPHIIt();
					}
				}

				Result->insertInto(InstParent, InsertPos);

				// Push the new instruction and any users onto the worklist.
				Worklist.pushUsersToWorkList(*Result);
				Worklist.push(Result);

				static_cast<DerivedT*>(this)->eraseInstFromFunction(*I);
			} else {
				LLVM_DEBUG(
						llvm::dbgs() << DEBUG_TYPE_SHORT ": Mod = " << OrigI << '\n' << "    New = " << *I << '\n');

				// If the instruction was modified, it's possible that it is now dead.
				// if so, remove it.
				if (llvm::isInstructionTriviallyDead(I, &TLI)) {
					static_cast<DerivedT*>(this)->eraseInstFromFunction(*I);
				} else {
					Worklist.pushUsersToWorkList(*I);
					Worklist.push(I);
				}
			}
			MadeIRChange = true;
			if (_dbgIrInstrCombineChangeCallbackFn) {
 				assert(lastOptRuleName);
				auto _lastOptRuleName = std::string(lastOptRuleName);
				onChangeCallback(_lastOptRuleName, F);
				lastOptRuleName = nullptr;
			}
		}
	}

	Worklist.zap();
	return MadeIRChange;
}


}
