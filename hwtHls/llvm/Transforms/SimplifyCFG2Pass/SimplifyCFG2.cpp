#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2.h>

#include <map>

#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/ConstantFolding.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/IR/ProfDataUtils.h>
#include <llvm/Support/Debug.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Analysis/AssumptionCache.h>

#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchSuccessorHoistCode.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchToSelect.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_SwitchLikeCmpToSwitch.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFGUtils.h>


#define DEBUG_TYPE "simplifycfg2"

using namespace llvm;

namespace hwtHls {

/// This class implements a stable ordering of constant
/// integers that does not depend on their address.  This is important for
/// applications that sort ConstantInt's to ensure uniqueness.
struct ConstantIntOrdering {
  bool operator()(const ConstantInt *LHS, const ConstantInt *RHS) const {
    return LHS->getValue().ult(RHS->getValue());
  }
};

/// Extract ConstantInt from value, looking through IntToPtr
/// and PointerNullValue. Return NULL if value is not a constant int.
static ConstantInt *GetConstantInt(Value *V, const DataLayout &DL) {
  // Normal constant int.
  ConstantInt *CI = dyn_cast<ConstantInt>(V);
  if (CI || !isa<Constant>(V) || !V->getType()->isPointerTy() ||
      DL.isNonIntegralPointerType(V->getType()))
    return CI;

  // This is some kind of pointer constant. Turn it into a pointer-sized
  // ConstantInt if possible.
  IntegerType *PtrTy = cast<IntegerType>(DL.getIntPtrType(V->getType()));

  // Null pointer means 0, see SelectionDAGBuilder::getValue(const Value*).
  if (isa<ConstantPointerNull>(V))
    return ConstantInt::get(PtrTy, 0);

  // IntToPtr const int.
  if (ConstantExpr *CE = dyn_cast<ConstantExpr>(V))
    if (CE->getOpcode() == Instruction::IntToPtr)
      if (ConstantInt *CI = dyn_cast<ConstantInt>(CE->getOperand(0))) {
        // The constant is very likely to have the right type already.
        if (CI->getType() == PtrTy)
          return CI;
        else
          return cast<ConstantInt>(
              ConstantFoldIntegerCast(CI, PtrTy, /*isSigned=*/false, DL));
      }
  return nullptr;
}

/// Get Weights of a given terminator, the default weight is at the front
/// of the vector. If TI is a conditional eq, we need to swap the branch-weight
/// metadata.
static void GetBranchWeights(Instruction *TI,
                             SmallVectorImpl<uint64_t> &Weights) {
  MDNode *MD = TI->getMetadata(LLVMContext::MD_prof);
  assert(MD);
  for (unsigned i = 1, e = MD->getNumOperands(); i < e; ++i) {
    ConstantInt *CI = mdconst::extract<ConstantInt>(MD->getOperand(i));
    Weights.push_back(CI->getValue().getZExtValue());
  }

  // If TI is a conditional eq, the default case is the false case,
  // and the corresponding branch-weight data is at index 2. We swap the
  // default weight to be the first entry.
  if (BranchInst *BI = dyn_cast<BranchInst>(TI)) {
    assert(Weights.size() == 2);
    ICmpInst *ICI = cast<ICmpInst>(BI->getCondition());
    if (ICI->getPredicate() == ICmpInst::ICMP_EQ)
      std::swap(Weights.front(), Weights.back());
  }
}

/// Update PHI nodes in Succ to indicate that there will now be entries in it
/// from the 'NewPred' block. The values that will be flowing into the PHI nodes
/// will be the same as those coming in from ExistPred, an existing predecessor
/// of Succ.
static void AddPredecessorToBlock(BasicBlock *Succ, BasicBlock *NewPred,
                                  BasicBlock *ExistPred,
                                  MemorySSAUpdater *MSSAU = nullptr) {
  for (PHINode &PN : Succ->phis())
    PN.addIncoming(PN.getIncomingValueForBlock(ExistPred), NewPred);
  if (MSSAU)
    if (auto *MPhi = MSSAU->getMemorySSA()->getMemoryAccess(Succ))
      MPhi->addIncoming(MPhi->getIncomingValueForBlock(ExistPred), NewPred);
}

/// Keep halving the weights until all can fit in uint32_t.
static void FitWeights(MutableArrayRef<uint64_t> Weights) {
  uint64_t Max = *std::max_element(Weights.begin(), Weights.end());
  if (Max > UINT_MAX) {
    unsigned Offset = 32 - llvm::countl_zero(Max);
    for (uint64_t &I : Weights)
      I >>= Offset;
  }
}

// Set branch weights on SwitchInst. This sets the metadata if there is at
// least one non-zero weight.
static void setBranchWeights(SwitchInst *SI, ArrayRef<uint32_t> Weights) {
  // Check that there is at least one non-zero weight. Otherwise, pass
  // nullptr to setMetadata which will erase the existing metadata.
  MDNode *N = nullptr;
  if (llvm::any_of(Weights, [](uint32_t W) { return W != 0; }))
    N = MDBuilder(SI->getParent()->getContext()).createBranchWeights(Weights);
  SI->setMetadata(LLVMContext::MD_prof, N);
}

static void EraseTerminatorAndDCECond(Instruction *TI,
                                      MemorySSAUpdater *MSSAU = nullptr) {
  Instruction *Cond = nullptr;
  if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
    Cond = dyn_cast<Instruction>(SI->getCondition());
  } else if (BranchInst *BI = dyn_cast<BranchInst>(TI)) {
    if (BI->isConditional())
      Cond = dyn_cast<Instruction>(BI->getCondition());
  } else if (IndirectBrInst *IBI = dyn_cast<IndirectBrInst>(TI)) {
    Cond = dyn_cast<Instruction>(IBI->getAddress());
  }

  TI->eraseFromParent();
  if (Cond)
    RecursivelyDeleteTriviallyDeadInstructions(Cond, nullptr, MSSAU);
}


static bool passingValueIsAlwaysUndefined(Value *V, Instruction *I, bool PtrValueMayBeModified = false);


/// Check if passing a value to an instruction will cause undefined behavior.
static bool passingValueIsAlwaysUndefined(Value *V, Instruction *I, bool PtrValueMayBeModified) {
  Constant *C = dyn_cast<Constant>(V);
  if (!C)
    return false;

  if (I->use_empty())
    return false;

  if (C->isNullValue() || isa<UndefValue>(C)) {
    // Only look at the first use, avoid hurting compile time with long uselists
    auto *Use = cast<Instruction>(*I->user_begin());
    // Bail out if Use is not in the same BB as I or Use == I or Use comes
    // before I in the block. The latter two can be the case if Use is a PHI
    // node.
    if (Use->getParent() != I->getParent() || Use == I || Use->comesBefore(I))
      return false;

    // Now make sure that there are no instructions in between that can alter
    // control flow (eg. calls)
    auto InstrRange =
        make_range(std::next(I->getIterator()), Use->getIterator());
    if (any_of(InstrRange, [](Instruction &I) {
          return !isGuaranteedToTransferExecutionToSuccessor(&I);
        }))
      return false;

    // Look through GEPs. A load from a GEP derived from NULL is still undefined
    if (GetElementPtrInst *GEP = dyn_cast<GetElementPtrInst>(Use))
      if (GEP->getPointerOperand() == I) {
        if (!GEP->isInBounds() || !GEP->hasAllZeroIndices())
          PtrValueMayBeModified = true;
        return passingValueIsAlwaysUndefined(V, GEP, PtrValueMayBeModified);
      }

    // Look through bitcasts.
    if (BitCastInst *BC = dyn_cast<BitCastInst>(Use))
      return passingValueIsAlwaysUndefined(V, BC, PtrValueMayBeModified);

    // Load from null is undefined.
    if (LoadInst *LI = dyn_cast<LoadInst>(Use))
      if (!LI->isVolatile())
        return !NullPointerIsDefined(LI->getFunction(),
                                     LI->getPointerAddressSpace());

    // Store to null is undefined.
    if (StoreInst *SI = dyn_cast<StoreInst>(Use))
      if (!SI->isVolatile())
        return (!NullPointerIsDefined(SI->getFunction(),
                                      SI->getPointerAddressSpace())) &&
               SI->getPointerOperand() == I;

    if (auto *CB = dyn_cast<CallBase>(Use)) {
      if (C->isNullValue() && NullPointerIsDefined(CB->getFunction()))
        return false;
      // A call to null is undefined.
      if (CB->getCalledOperand() == I)
        return true;

      if (C->isNullValue()) {
        for (const llvm::Use &Arg : CB->args())
          if (Arg == I) {
            unsigned ArgIdx = CB->getArgOperandNo(&Arg);
            if (CB->isPassingUndefUB(ArgIdx) &&
                CB->paramHasAttr(ArgIdx, Attribute::NonNull)) {
              // Passing null to a nonnnull+noundef argument is undefined.
              return !PtrValueMayBeModified;
            }
          }
      } else if (isa<UndefValue>(C)) {
        // Passing undef to a noundef argument is undefined.
        for (const llvm::Use &Arg : CB->args())
          if (Arg == I) {
            unsigned ArgIdx = CB->getArgOperandNo(&Arg);
            if (CB->isPassingUndefUB(ArgIdx)) {
              // Passing undef to a noundef argument is undefined.
              return true;
            }
          }
      }
    }
  }
  return false;
}

/// If BB has an incoming value that will always trigger undefined behavior
/// (eg. null pointer dereference), remove the branch leading here.
static bool removeUndefIntroducingPredecessor(BasicBlock *BB,
                                              DomTreeUpdater *DTU,
                                              AssumptionCache *AC) {
  for (PHINode &PHI : BB->phis())
    for (unsigned i = 0, e = PHI.getNumIncomingValues(); i != e; ++i)
      if (passingValueIsAlwaysUndefined(PHI.getIncomingValue(i), &PHI)) {
        BasicBlock *Predecessor = PHI.getIncomingBlock(i);
        Instruction *T = Predecessor->getTerminator();
        IRBuilder<> Builder(T);
        if (BranchInst *BI = dyn_cast<BranchInst>(T)) {
          BB->removePredecessor(Predecessor);
          // Turn unconditional branches into unreachables and remove the dead
          // destination from conditional branches.
          if (BI->isUnconditional())
            Builder.CreateUnreachable();
          else {
            // Preserve guarding condition in assume, because it might not be
            // inferrable from any dominating condition.
            Value *Cond = BI->getCondition();
            CallInst *Assumption;
            if (BI->getSuccessor(0) == BB)
              Assumption = Builder.CreateAssumption(Builder.CreateNot(Cond));
            else
              Assumption = Builder.CreateAssumption(Cond);
            if (AC)
              AC->registerAssumption(cast<AssumeInst>(Assumption));
            Builder.CreateBr(BI->getSuccessor(0) == BB ? BI->getSuccessor(1)
                                                       : BI->getSuccessor(0));
          }
          BI->eraseFromParent();
          if (DTU)
            DTU->applyUpdates({{DominatorTree::Delete, Predecessor, BB}});
          return true;
        } else if (SwitchInst *SI = dyn_cast<SwitchInst>(T)) {
          // Redirect all branches leading to UB into
          // a newly created unreachable block.
          BasicBlock *Unreachable = BasicBlock::Create(
              Predecessor->getContext(), "unreachable", BB->getParent(), BB);
          Builder.SetInsertPoint(Unreachable);
          // The new block contains only one instruction: Unreachable
          Builder.CreateUnreachable();
          for (const auto &Case : SI->cases())
            if (Case.getCaseSuccessor() == BB) {
              BB->removePredecessor(Predecessor);
              Case.setSuccessor(Unreachable);
            }
          if (SI->getDefaultDest() == BB) {
            BB->removePredecessor(Predecessor);
            SI->setDefaultDest(Unreachable);
          }

          if (DTU)
            DTU->applyUpdates(
                { { DominatorTree::Insert, Predecessor, Unreachable },
                  { DominatorTree::Delete, Predecessor, BB } });
          return true;
        }
      }

  return false;
}


bool SimplifyCFGOpt2::PerformValueComparisonIntoPredecessorFolding(
    Instruction *TI, Value *&CV, Instruction *PTI, IRBuilder<> &Builder) {
  BasicBlock *BB = TI->getParent();
  BasicBlock *Pred = PTI->getParent();

  SmallVector<DominatorTree::UpdateType, 32> Updates;

  // Figure out which 'cases' to copy from SI to PSI.
  std::vector<ValueEqualityComparisonCase> BBCases;
  BasicBlock *BBDefault = GetValueEqualityComparisonCases(TI, BBCases);

  std::vector<ValueEqualityComparisonCase> PredCases;
  BasicBlock *PredDefault = GetValueEqualityComparisonCases(PTI, PredCases);

  // Based on whether the default edge from PTI goes to BB or not, fill in
  // PredCases and PredDefault with the new switch cases we would like to
  // build.
  SmallMapVector<BasicBlock *, int, 8> NewSuccessors;

  // Update the branch weight metadata along the way
  SmallVector<uint64_t, 8> Weights;
  bool PredHasWeights = hasBranchWeightMD(*PTI);
  bool SuccHasWeights = hasBranchWeightMD(*TI);

  if (PredHasWeights) {
    GetBranchWeights(PTI, Weights);
    // branch-weight metadata is inconsistent here.
    if (Weights.size() != 1 + PredCases.size())
      PredHasWeights = SuccHasWeights = false;
  } else if (SuccHasWeights)
    // If there are no predecessor weights but there are successor weights,
    // populate Weights with 1, which will later be scaled to the sum of
    // successor's weights
    Weights.assign(1 + PredCases.size(), 1);

  SmallVector<uint64_t, 8> SuccWeights;
  if (SuccHasWeights) {
    GetBranchWeights(TI, SuccWeights);
    // branch-weight metadata is inconsistent here.
    if (SuccWeights.size() != 1 + BBCases.size())
      PredHasWeights = SuccHasWeights = false;
  } else if (PredHasWeights)
    SuccWeights.assign(1 + BBCases.size(), 1);

  if (PredDefault == BB) {
    // If this is the default destination from PTI, only the edges in TI
    // that don't occur in PTI, or that branch to BB will be activated.
    std::set<ConstantInt *, ConstantIntOrdering> PTIHandled;
    for (unsigned i = 0, e = PredCases.size(); i != e; ++i)
      if (PredCases[i].Dest != BB)
        PTIHandled.insert(PredCases[i].Value);
      else {
        // The default destination is BB, we don't need explicit targets.
        std::swap(PredCases[i], PredCases.back());

        if (PredHasWeights || SuccHasWeights) {
          // Increase weight for the default case.
          Weights[0] += Weights[i + 1];
          std::swap(Weights[i + 1], Weights.back());
          Weights.pop_back();
        }

        PredCases.pop_back();
        --i;
        --e;
      }

    // Reconstruct the new switch statement we will be building.
    if (PredDefault != BBDefault) {
      PredDefault->removePredecessor(Pred);
      if (DTU && PredDefault != BB)
        Updates.push_back({DominatorTree::Delete, Pred, PredDefault});
      PredDefault = BBDefault;
      ++NewSuccessors[BBDefault];
    }

    unsigned CasesFromPred = Weights.size();
    uint64_t ValidTotalSuccWeight = 0;
    for (unsigned i = 0, e = BBCases.size(); i != e; ++i)
      if (!PTIHandled.count(BBCases[i].Value) && BBCases[i].Dest != BBDefault) {
        PredCases.push_back(BBCases[i]);
        ++NewSuccessors[BBCases[i].Dest];
        if (SuccHasWeights || PredHasWeights) {
          // The default weight is at index 0, so weight for the ith case
          // should be at index i+1. Scale the cases from successor by
          // PredDefaultWeight (Weights[0]).
          Weights.push_back(Weights[0] * SuccWeights[i + 1]);
          ValidTotalSuccWeight += SuccWeights[i + 1];
        }
      }

    if (SuccHasWeights || PredHasWeights) {
      ValidTotalSuccWeight += SuccWeights[0];
      // Scale the cases from predecessor by ValidTotalSuccWeight.
      for (unsigned i = 1; i < CasesFromPred; ++i)
        Weights[i] *= ValidTotalSuccWeight;
      // Scale the default weight by SuccDefaultWeight (SuccWeights[0]).
      Weights[0] *= SuccWeights[0];
    }
  } else {
    // If this is not the default destination from PSI, only the edges
    // in SI that occur in PSI with a destination of BB will be
    // activated.
    std::set<ConstantInt *, ConstantIntOrdering> PTIHandled;
    std::map<ConstantInt *, uint64_t> WeightsForHandled;
    for (unsigned i = 0, e = PredCases.size(); i != e; ++i)
      if (PredCases[i].Dest == BB) {
        PTIHandled.insert(PredCases[i].Value);

        if (PredHasWeights || SuccHasWeights) {
          WeightsForHandled[PredCases[i].Value] = Weights[i + 1];
          std::swap(Weights[i + 1], Weights.back());
          Weights.pop_back();
        }

        std::swap(PredCases[i], PredCases.back());
        PredCases.pop_back();
        --i;
        --e;
      }

    // Okay, now we know which constants were sent to BB from the
    // predecessor.  Figure out where they will all go now.
    for (unsigned i = 0, e = BBCases.size(); i != e; ++i)
      if (PTIHandled.count(BBCases[i].Value)) {
        // If this is one we are capable of getting...
        if (PredHasWeights || SuccHasWeights)
          Weights.push_back(WeightsForHandled[BBCases[i].Value]);
        PredCases.push_back(BBCases[i]);
        ++NewSuccessors[BBCases[i].Dest];
        PTIHandled.erase(BBCases[i].Value); // This constant is taken care of
      }

    // If there are any constants vectored to BB that TI doesn't handle,
    // they must go to the default destination of TI.
    for (ConstantInt *I : PTIHandled) {
      if (PredHasWeights || SuccHasWeights)
        Weights.push_back(WeightsForHandled[I]);
      PredCases.push_back(ValueEqualityComparisonCase(I, BBDefault));
      ++NewSuccessors[BBDefault];
    }
  }

  // Okay, at this point, we know which new successor Pred will get.  Make
  // sure we update the number of entries in the PHI nodes for these
  // successors.
  SmallPtrSet<BasicBlock *, 2> SuccsOfPred;
  if (DTU) {
    SuccsOfPred = {succ_begin(Pred), succ_end(Pred)};
    Updates.reserve(Updates.size() + NewSuccessors.size());
  }
  for (const std::pair<BasicBlock *, int /*Num*/> &NewSuccessor :
       NewSuccessors) {
    for (auto I : seq(NewSuccessor.second)) {
      (void)I;
      AddPredecessorToBlock(NewSuccessor.first, Pred, BB);
    }
    if (DTU && !SuccsOfPred.contains(NewSuccessor.first))
      Updates.push_back({DominatorTree::Insert, Pred, NewSuccessor.first});
  }

  Builder.SetInsertPoint(PTI);
  // Convert pointer to int before we switch.
  if (CV->getType()->isPointerTy()) {
    CV =
        Builder.CreatePtrToInt(CV, DL.getIntPtrType(CV->getType()), "magicptr");
  }

  // Now that the successors are updated, create the new Switch instruction.
  SwitchInst *NewSI = Builder.CreateSwitch(CV, PredDefault, PredCases.size());
  NewSI->setDebugLoc(PTI->getDebugLoc());
  for (ValueEqualityComparisonCase &V : PredCases)
    NewSI->addCase(V.Value, V.Dest);

  if (PredHasWeights || SuccHasWeights) {
    // Halve the weights if any of them cannot fit in an uint32_t
    FitWeights(Weights);

    SmallVector<uint32_t, 8> MDWeights(Weights.begin(), Weights.end());

    setBranchWeights(NewSI, MDWeights);
  }

  EraseTerminatorAndDCECond(PTI);

  // Okay, last check.  If BB is still a successor of PSI, then we must
  // have an infinite loop case.  If so, add an infinitely looping block
  // to handle the case to preserve the behavior of the code.
  BasicBlock *InfLoopBlock = nullptr;
  for (unsigned i = 0, e = NewSI->getNumSuccessors(); i != e; ++i)
    if (NewSI->getSuccessor(i) == BB) {
      if (!InfLoopBlock) {
        // Insert it at the end of the function, because it's either code,
        // or it won't matter if it's hot. :)
        InfLoopBlock =
            BasicBlock::Create(BB->getContext(), "infloop", BB->getParent());
        BranchInst::Create(InfLoopBlock, InfLoopBlock);
        if (DTU)
          Updates.push_back(
              {DominatorTree::Insert, InfLoopBlock, InfLoopBlock});
      }
      NewSI->setSuccessor(i, InfLoopBlock);
    }

  if (DTU) {
    if (InfLoopBlock)
      Updates.push_back({DominatorTree::Insert, Pred, InfLoopBlock});

    Updates.push_back({DominatorTree::Delete, Pred, BB});

    DTU->applyUpdates(Updates);
  }

  //++NumFoldValueComparisonIntoPredecessors;
  return true;
}


/// Given a value comparison instruction,
/// decode all of the 'cases' that it represents and return the 'default' block.
BasicBlock* SimplifyCFGOpt2::GetValueEqualityComparisonCases(
    Instruction *TI, std::vector<ValueEqualityComparisonCase> &Cases) {
  if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
    Cases.reserve(SI->getNumCases());
    for (auto Case : SI->cases())
      Cases.push_back(ValueEqualityComparisonCase(Case.getCaseValue(),
                                                  Case.getCaseSuccessor()));
    return SI->getDefaultDest();
  }

  BranchInst *BI = cast<BranchInst>(TI);
  ICmpInst *ICI = cast<ICmpInst>(BI->getCondition());
  BasicBlock *Succ = BI->getSuccessor(ICI->getPredicate() == ICmpInst::ICMP_NE);
  Cases.push_back(ValueEqualityComparisonCase(
      GetConstantInt(ICI->getOperand(1), DL), Succ));
  return BI->getSuccessor(ICI->getPredicate() == ICmpInst::ICMP_EQ);
}


/// Return true if all the PHI nodes in the basic block \p BB
/// receive compatible (identical) incoming values when coming from
/// all of the predecessor blocks that are specified in \p IncomingBlocks.
///
/// Note that if the values aren't exactly identical, but \p EquivalenceSet
/// is provided, and *both* of the values are present in the set,
/// then they are considered equal.
static bool IncomingValuesAreCompatible(
    BasicBlock *BB, ArrayRef<BasicBlock *> IncomingBlocks,
    SmallPtrSetImpl<Value *> *EquivalenceSet = nullptr) {
  assert(IncomingBlocks.size() == 2 &&
         "Only for a pair of incoming blocks at the time!");

  // FIXME: it is okay if one of the incoming values is an `undef` value,
  //        iff the other incoming value is guaranteed to be a non-poison value.
  // FIXME: it is okay if one of the incoming values is a `poison` value.
  return all_of(BB->phis(), [IncomingBlocks, EquivalenceSet](PHINode &PN) {
    Value *IV0 = PN.getIncomingValueForBlock(IncomingBlocks[0]);
    Value *IV1 = PN.getIncomingValueForBlock(IncomingBlocks[1]);
    if (IV0 == IV1)
      return true;
    if (EquivalenceSet && EquivalenceSet->contains(IV0) &&
        EquivalenceSet->contains(IV1))
      return true;
    return false;
  });
}

/// Return true if it is safe to merge these two
/// terminator instructions together.
static bool
SafeToMergeTerminators(Instruction *SI1, Instruction *SI2,
                       SmallSetVector<BasicBlock *, 4> *FailBlocks = nullptr) {
  if (SI1 == SI2)
    return false; // Can't merge with self!

  // It is not safe to merge these two switch instructions if they have a common
  // successor, and if that successor has a PHI node, and if *that* PHI node has
  // conflicting incoming values from the two switch blocks.
  BasicBlock *SI1BB = SI1->getParent();
  BasicBlock *SI2BB = SI2->getParent();

  SmallPtrSet<BasicBlock *, 16> SI1Succs(succ_begin(SI1BB), succ_end(SI1BB));
  bool Fail = false;
  for (BasicBlock *Succ : successors(SI2BB)) {
    if (!SI1Succs.count(Succ))
      continue;
    if (IncomingValuesAreCompatible(Succ, {SI1BB, SI2BB}))
      continue;
    Fail = true;
    if (FailBlocks)
      FailBlocks->insert(Succ);
    else
      break;
  }

  return !Fail;
}

/// Return true if the specified terminator checks
/// to see if a value is equal to constant integer value.
Value* SimplifyCFGOpt2::isValueEqualityComparison(Instruction *TI,
		bool checkParentPredecessors) {
	Value *CV = nullptr;
	if (SwitchInst *SI = dyn_cast<SwitchInst>(TI)) {
		// Do not permit merging of large switch instructions into their
		// predecessors unless there is only one predecessor.
		if (!checkParentPredecessors
				|| !SI->getParent()->hasNPredecessorsOrMore(
						128 / SI->getNumSuccessors()))
			CV = SI->getCondition();
	} else if (BranchInst *BI = dyn_cast<BranchInst>(TI))
		if (BI->isConditional() && BI->getCondition()->hasOneUse())
			if (ICmpInst *ICI = dyn_cast<ICmpInst>(BI->getCondition())) {
				if (ICI->isEquality() && GetConstantInt(ICI->getOperand(1), DL))
					CV = ICI->getOperand(0);
			}

	// Unwrap any lossless ptrtoint cast.
	if (CV) {
		if (PtrToIntInst *PTII = dyn_cast<PtrToIntInst>(CV)) {
			Value *Ptr = PTII->getPointerOperand();
			if (PTII->getType() == DL.getIntPtrType(Ptr->getType()))
				CV = Ptr;
		}
	}
	return CV;
}

/// The specified terminator is a value equality comparison instruction
/// (either a switch or a branch on "X == c").
/// See if any of the predecessors of the terminator block are value comparisons
/// on the same value.  If so, and if safe to do so, fold them together.
bool SimplifyCFGOpt2::FoldValueComparisonIntoPredecessors(Instruction *TI,
		IRBuilder<> &Builder) {
	BasicBlock *BB = TI->getParent();
	Value *CV = isValueEqualityComparison(TI, false); // CondVal
	assert(CV && "Not a comparison?");

	bool Changed = false;

	SmallSetVector<BasicBlock*, 16> Preds(pred_begin(BB), pred_end(BB));
	while (!Preds.empty()) {
		BasicBlock *Pred = Preds.pop_back_val();
		Instruction *PTI = Pred->getTerminator();

		// Don't try to fold into itself.
		if (Pred == BB)
			continue;

		// See if the predecessor is a comparison with the same value.
		Value *PCV = isValueEqualityComparison(PTI, false); // PredCondVal
		if (PCV != CV)
			continue;

		SmallSetVector<BasicBlock*, 4> FailBlocks;
		if (!SafeToMergeTerminators(TI, PTI, &FailBlocks)) {
			for (auto *Succ : FailBlocks) {
				if (!SplitBlockPredecessors(Succ, TI->getParent(),
						".fold.split", DTU))
					return false;
			}
		}

		PerformValueComparisonIntoPredecessorFolding(TI, CV, PTI, Builder);
		Changed = true;
	}
	return Changed;
}

bool SimplifyCFGOpt2::simplifySwitch(SwitchInst *SI, IRBuilder<> &Builder) {
	BasicBlock *BB = SI->getParent();

	if (isValueEqualityComparison(SI, false)) {
		// If the block only contains the switch, see if we can fold the block
		// away into any preds.
		if (SI == &*BB->instructionsWithoutDebug(false).begin())
			if (FoldValueComparisonIntoPredecessors(SI, Builder))
				return requestResimplify();
	}
	bool everySucDominated = true;
	bool everySucHasOnlyThisPred = true;
	auto BBSuccessors = successors(BB);
	for (BasicBlock *Succ : BBSuccessors) {
		if (Succ->hasAddressTaken()) {
			everySucDominated = false;
			everySucHasOnlyThisPred = false;
			break;
		}
		if (Succ->getUniquePredecessor() == BB)
			continue;
		everySucHasOnlyThisPred = false;

		bool allSucPredecessorsAreDominatedByBB = true;
		for (auto *SuccPred : predecessors(Succ)) {
			if (SuccPred != BB
					&& std::find(BBSuccessors.begin(), BBSuccessors.end(),
							SuccPred) == BBSuccessors.end()) {
				allSucPredecessorsAreDominatedByBB = false;
				break;
			}
		}
		if (!allSucPredecessorsAreDominatedByBB) {
			everySucDominated = false;
			break;
		}
	}
	if (Options.HoistCommonInsts) {
		if (everySucHasOnlyThisPred
				&& HoistFromSwitchSuccessors(SI, TTI,
						LlvmHoistCommonSkipLimit)) {
			return requestResimplify();
		}
	}
	if (everySucDominated && trySwitchToSelectOrRomLoad(SI, Builder, *DTU))
		return requestResimplify();

	return false;
}
bool SimplifyCFGOpt2::simplifyBr(BranchInst *BI, IRBuilder<> &Builder) {
	if (Options.HoistCommonInsts) {
		if (DTU->hasDomTree()
				&& tryHoistFromCheapBlocksWithcSwitchLikeCmpBr(BI, Builder,
						DTU)) {
			return requestResimplify();
		}
	}
	return false;
}
bool SimplifyCFGOpt2::simplifyOnce(BasicBlock *BB) {
	bool Changed = false;

	assert(BB && BB->getParent() && "Block not embedded in function!");
	assert(BB->getTerminator() && "Degenerate basic block encountered!");

	// Remove basic blocks that have no predecessors (except the entry block)...
	// or that just have themself as a predecessor.  These are unreachable.
	if ((pred_empty(BB) && BB != &BB->getParent()->getEntryBlock())
			|| BB->getSinglePredecessor() == BB) {
		LLVM_DEBUG(dbgs() << "Removing BB: \n" << *BB);
		DeleteDeadBlock(BB, DTU);
		return true;
	}
	if (Options.HoistCheapInsts) {
		auto *PredBB = BB->getSinglePredecessor();
		if (PredBB && PredBB != BB) {
			Changed |= tryHoistCheapInstsAtBlockBegin(*BB,
					PredBB->getTerminator());
		}
	}
	// Check to see if we can constant propagate this terminator instruction
	// away...
	Changed |= ConstantFoldTerminator(BB, /*DeleteDeadConditions=*/true,
	/*TLI=*/nullptr, DTU);

	// Check for and eliminate duplicate PHI nodes in this block.
	Changed |= EliminateDuplicatePHINodes(BB);

	// Check for and remove branches that will always cause undefined behavior.
	if (removeUndefIntroducingPredecessor(BB, DTU, Options.AC))
		return requestResimplify();

	// Merge basic blocks into their predecessor if there is only one distinct
	// pred, and if there is only one distinct successor of the predecessor, and
	// if there are no PHI nodes.
	if (MergeBlockIntoPredecessor(BB, DTU))
		return true;

	IRBuilder<> Builder(BB);

	Instruction *Terminator = BB->getTerminator();
	Builder.SetInsertPoint(Terminator);
	switch (Terminator->getOpcode()) {
	case Instruction::Switch:
		Changed |= simplifySwitch(cast<SwitchInst>(Terminator), Builder);
		break;
	case Instruction::Br:
		Changed |= simplifyBr(cast<BranchInst>(Terminator), Builder);
		break;
	}
	return Changed;
}

}
