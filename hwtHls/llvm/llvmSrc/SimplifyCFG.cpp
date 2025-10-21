#include <hwtHls/llvm/llvmSrc/SimplifyCFG.h>

#include <llvm/ADT/APInt.h>
#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/DenseMap.h>
#include <llvm/ADT/MapVector.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/Sequence.h>
#include <llvm/ADT/SetOperations.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/ADT/StringRef.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/CaptureTracking.h>
#include <llvm/Analysis/ConstantFolding.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/GuardUtils.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/MemorySSA.h>
#include <llvm/Analysis/MemorySSAUpdater.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Constant.h>
#include <llvm/IR/ConstantRange.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DataLayout.h>
#include <llvm/IR/DebugInfo.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/IR/GlobalVariable.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/IR/Metadata.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/NoFolder.h>
#include <llvm/IR/Operator.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/ProfDataUtils.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Use.h>
#include <llvm/IR/User.h>
#include <llvm/IR/Value.h>
#include <llvm/IR/ValueHandle.h>
#include <llvm/Support/BranchProbability.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Support/KnownBits.h>
#include <llvm/Support/MathExtras.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Utils/ValueMapper.h>

using namespace llvm;
using namespace PatternMatch;

#define DEBUG_TYPE "hwthls-simplifycfg"

cl::opt<bool> llvm::RequireAndPreserveDomTree(
    "hwthls-simplifycfg-require-and-preserve-domtree", cl::Hidden,

    cl::desc("Temorary development switch used to gradually uplift SimplifyCFG "
             "into preserving DomTree,"));

// Chosen as 2 so as to be cheap, but still to have enough power to fold
// a select, so the "clamp" idiom (of a min followed by a max) will be caught.
// To catch this, we need to fold a compare and a select, hence '2' being the
// minimum reasonable default.
static cl::opt<unsigned> PHINodeFoldingThreshold(
    "hwthls-phi-node-folding-threshold", cl::Hidden, cl::init(2),
    cl::desc(
        "Control the amount of phi node folding to perform (default = 2)"));

static cl::opt<bool> MergeCondStores(
    "hwthls-simplifycfg-merge-cond-stores", cl::Hidden, cl::init(true),
    cl::desc("Hoist conditional stores even if an unconditional store does not "
             "precede - hoist multiple conditional stores into a single "
             "predicated store"));

static cl::opt<bool> MergeCondStoresAggressively(
    "hwthls-simplifycfg-merge-cond-stores-aggressively", cl::Hidden, cl::init(false),
    cl::desc("When merging conditional stores, do so even if the resultant "
             "basic blocks are unlikely to be if-converted as a result"));



namespace hwtHls {

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

// Similar to the above, but for branch and select instructions that take
// exactly 2 weights.
static void setBranchWeights(Instruction *I, uint32_t TrueWeight,
                             uint32_t FalseWeight) {
  assert(isa<BranchInst>(I) || isa<SelectInst>(I));
  // Check that there is at least one non-zero weight. Otherwise, pass
  // nullptr to setMetadata which will erase the existing metadata.
  MDNode *N = nullptr;
  if (TrueWeight || FalseWeight)
    N = MDBuilder(I->getParent()->getContext())
            .createBranchWeights(TrueWeight, FalseWeight);
  I->setMetadata(LLVMContext::MD_prof, N);
}

static Value *createLogicalOp(IRBuilderBase &Builder,
                              Instruction::BinaryOps Opc, Value *LHS,
                              Value *RHS, const Twine &Name = "") {
  // Try to relax logical op to binary op.
  if (impliesPoison(RHS, LHS))
    return Builder.CreateBinOp(Opc, LHS, RHS, Name);
  if (Opc == Instruction::And)
    return Builder.CreateLogicalAnd(LHS, RHS, Name);
  if (Opc == Instruction::Or)
    return Builder.CreateLogicalOr(LHS, RHS, Name);
  llvm_unreachable("Invalid logical opcode");
}

/// Return true if either PBI or BI has branch weight available, and store
/// the weights in {Pred|Succ}{True|False}Weight. If one of PBI and BI does
/// not have branch weight, use 1:1 as its weight.
static bool extractPredSuccWeights(BranchInst *PBI, BranchInst *BI,
                                   uint64_t &PredTrueWeight,
                                   uint64_t &PredFalseWeight,
                                   uint64_t &SuccTrueWeight,
                                   uint64_t &SuccFalseWeight) {
  bool PredHasWeights =
      extractBranchWeights(*PBI, PredTrueWeight, PredFalseWeight);
  bool SuccHasWeights =
      extractBranchWeights(*BI, SuccTrueWeight, SuccFalseWeight);
  if (PredHasWeights || SuccHasWeights) {
    if (!PredHasWeights)
      PredTrueWeight = PredFalseWeight = 1;
    if (!SuccHasWeights)
      SuccTrueWeight = SuccFalseWeight = 1;
    return true;
  } else {
    return false;
  }
}

// If there is only one store in BB1 and BB2, return it, otherwise return
// nullptr.
static StoreInst *findUniqueStoreInBlocks(BasicBlock *BB1, BasicBlock *BB2) {
  StoreInst *S = nullptr;
  for (auto *BB : {BB1, BB2}) {
    if (!BB)
      continue;
    for (auto &I : *BB)
      if (auto *SI = dyn_cast<StoreInst>(&I)) {
        if (S)
          // Multiple stores seen.
          return nullptr;
        else
          S = SI;
      }
  }
  return S;
}

static Value *ensureValueAvailableInSuccessor(Value *V, BasicBlock *BB,
                                              Value *AlternativeV = nullptr) {
  // PHI is going to be a PHI node that allows the value V that is defined in
  // BB to be referenced in BB's only successor.
  //
  // If AlternativeV is nullptr, the only value we care about in PHI is V. It
  // doesn't matter to us what the other operand is (it'll never get used). We
  // could just create a new PHI with an undef incoming value, but that could
  // increase register pressure if EarlyCSE/InstCombine can't fold it with some
  // other PHI. So here we directly look for some PHI in BB's successor with V
  // as an incoming operand. If we find one, we use it, else we create a new
  // one.
  //
  // If AlternativeV is not nullptr, we care about both incoming values in PHI.
  // PHI must be exactly: phi <ty> [ %BB, %V ], [ %OtherBB, %AlternativeV]
  // where OtherBB is the single other predecessor of BB's only successor.
  PHINode *PHI = nullptr;
  BasicBlock *Succ = BB->getSingleSuccessor();

  for (auto I = Succ->begin(); isa<PHINode>(I); ++I)
    if (cast<PHINode>(I)->getIncomingValueForBlock(BB) == V) {
      PHI = cast<PHINode>(I);
      if (!AlternativeV)
        break;

      assert(Succ->hasNPredecessors(2));
      auto PredI = pred_begin(Succ);
      BasicBlock *OtherPredBB = *PredI == BB ? *++PredI : *PredI;
      if (PHI->getIncomingValueForBlock(OtherPredBB) == AlternativeV)
        break;
      PHI = nullptr;
    }
  if (PHI)
    return PHI;

  // If V is not an instruction defined in BB, just return it.
  if (!AlternativeV &&
      (!isa<Instruction>(V) || cast<Instruction>(V)->getParent() != BB))
    return V;

  PHI = PHINode::Create(V->getType(), 2, "simplifycfg.merge");
  PHI->insertBefore(Succ->begin());
  PHI->addIncoming(V, BB);
  for (BasicBlock *PredBB : predecessors(Succ))
    if (PredBB != BB)
      PHI->addIncoming(
          AlternativeV ? AlternativeV : PoisonValue::get(V->getType()), PredBB);
  return PHI;
}

static bool mergeConditionalStoreToAddress(
    BasicBlock *PTB, BasicBlock *PFB, BasicBlock *QTB, BasicBlock *QFB,
    BasicBlock *PostBB, Value *Address, bool InvertPCond, bool InvertQCond,
    DomTreeUpdater *DTU, const DataLayout &DL, const TargetTransformInfo &TTI) {
  // For every pointer, there must be exactly two stores, one coming from
  // PTB or PFB, and the other from QTB or QFB. We don't support more than one
  // store (to any address) in PTB,PFB or QTB,QFB.
  // FIXME: We could relax this restriction with a bit more work and performance
  // testing.
  StoreInst *PStore = findUniqueStoreInBlocks(PTB, PFB);
  StoreInst *QStore = findUniqueStoreInBlocks(QTB, QFB);
  if (!PStore || !QStore)
    return false;

  // Now check the stores are compatible.
  if (!QStore->isUnordered() || !PStore->isUnordered() ||
      PStore->getValueOperand()->getType() !=
          QStore->getValueOperand()->getType())
    return false;

  // Check that sinking the store won't cause program behavior changes. Sinking
  // the store out of the Q blocks won't change any behavior as we're sinking
  // from a block to its unconditional successor. But we're moving a store from
  // the P blocks down through the middle block (QBI) and past both QFB and QTB.
  // So we need to check that there are no aliasing loads or stores in
  // QBI, QTB and QFB. We also need to check there are no conflicting memory
  // operations between PStore and the end of its parent block.
  //
  // The ideal way to do this is to query AliasAnalysis, but we don't
  // preserve AA currently so that is dangerous. Be super safe and just
  // check there are no other memory operations at all.
  for (auto &I : *QFB->getSinglePredecessor())
    if (I.mayReadOrWriteMemory())
      return false;
  for (auto &I : *QFB)
    if (&I != QStore && I.mayReadOrWriteMemory())
      return false;
  if (QTB)
    for (auto &I : *QTB)
      if (&I != QStore && I.mayReadOrWriteMemory())
        return false;
  for (auto I = BasicBlock::iterator(PStore), E = PStore->getParent()->end();
       I != E; ++I)
    if (&*I != PStore && I->mayReadOrWriteMemory())
      return false;

  // If we're not in aggressive mode, we only optimize if we have some
  // confidence that by optimizing we'll allow P and/or Q to be if-converted.
  auto IsWorthwhile = [&](BasicBlock *BB, ArrayRef<StoreInst *> FreeStores) {
    if (!BB)
      return true;
    // Heuristic: if the block can be if-converted/phi-folded and the
    // instructions inside are all cheap (arithmetic/GEPs), it's worthwhile to
    // thread this store.
    InstructionCost Cost = 0;
    InstructionCost Budget =
        PHINodeFoldingThreshold * TargetTransformInfo::TCC_Basic;
    for (Instruction &I : BB->instructionsWithoutDebug(false)) {
      // Consider terminator instruction to be free.
      if (I.isTerminator())
        continue;
      // If this is one the stores that we want to speculate out of this BB,
      // then don't count it's cost, consider it to be free.
      if (auto *S = dyn_cast<StoreInst>(&I))
        if (llvm::find(FreeStores, S))
          continue;
      // Else, we have a white-list of instructions that we are ak speculating.
      if (!isa<BinaryOperator>(I) && !isa<GetElementPtrInst>(I))
        return false; // Not in white-list - not worthwhile folding.
      // And finally, if this is a non-free instruction that we are okay
      // speculating, ensure that we consider the speculation budget.
      Cost +=
          TTI.getInstructionCost(&I, TargetTransformInfo::TCK_SizeAndLatency);
      if (Cost > Budget)
        return false; // Eagerly refuse to fold as soon as we're out of budget.
    }
    assert(Cost <= Budget &&
           "When we run out of budget we will eagerly return from within the "
           "per-instruction loop.");
    return true;
  };

  const std::array<StoreInst *, 2> FreeStores = {PStore, QStore};
  if (!MergeCondStoresAggressively &&
      (!IsWorthwhile(PTB, FreeStores) || !IsWorthwhile(PFB, FreeStores) ||
       !IsWorthwhile(QTB, FreeStores) || !IsWorthwhile(QFB, FreeStores)))
    return false;

  // If PostBB has more than two predecessors, we need to split it so we can
  // sink the store.
  if (std::next(pred_begin(PostBB), 2) != pred_end(PostBB)) {
    // We know that QFB's only successor is PostBB. And QFB has a single
    // predecessor. If QTB exists, then its only successor is also PostBB.
    // If QTB does not exist, then QFB's only predecessor has a conditional
    // branch to QFB and PostBB.
    BasicBlock *TruePred = QTB ? QTB : QFB->getSinglePredecessor();
    BasicBlock *NewBB =
        SplitBlockPredecessors(PostBB, {QFB, TruePred}, "condstore.split", DTU);
    if (!NewBB)
      return false;
    PostBB = NewBB;
  }

  // OK, we're going to sink the stores to PostBB. The store has to be
  // conditional though, so first create the predicate.
  Value *PCond = cast<BranchInst>(PFB->getSinglePredecessor()->getTerminator())
                     ->getCondition();
  Value *QCond = cast<BranchInst>(QFB->getSinglePredecessor()->getTerminator())
                     ->getCondition();

  Value *PPHI = ensureValueAvailableInSuccessor(PStore->getValueOperand(),
                                                PStore->getParent());
  Value *QPHI = ensureValueAvailableInSuccessor(QStore->getValueOperand(),
                                                QStore->getParent(), PPHI);

  BasicBlock::iterator PostBBFirst = PostBB->getFirstInsertionPt();
  IRBuilder<> QB(PostBB, PostBBFirst);
  QB.SetCurrentDebugLocation(PostBBFirst->getStableDebugLoc());

  Value *PPred = PStore->getParent() == PTB ? PCond : QB.CreateNot(PCond);
  Value *QPred = QStore->getParent() == QTB ? QCond : QB.CreateNot(QCond);

  if (InvertPCond)
    PPred = QB.CreateNot(PPred);
  if (InvertQCond)
    QPred = QB.CreateNot(QPred);
  Value *CombinedPred = QB.CreateOr(PPred, QPred);

  BasicBlock::iterator InsertPt = QB.GetInsertPoint();
  auto *T = SplitBlockAndInsertIfThen(CombinedPred, InsertPt,
                                      /*Unreachable=*/false,
                                      /*BranchWeights=*/nullptr, DTU);

  QB.SetInsertPoint(T);
  StoreInst *SI = cast<StoreInst>(QB.CreateStore(QPHI, Address));
  SI->setAAMetadata(PStore->getAAMetadata().merge(QStore->getAAMetadata()));
  // Choose the minimum alignment. If we could prove both stores execute, we
  // could use biggest one.  In this case, though, we only know that one of the
  // stores executes.  And we don't know it's safe to take the alignment from a
  // store that doesn't execute.
  SI->setAlignment(std::min(PStore->getAlign(), QStore->getAlign()));

  QStore->eraseFromParent();
  PStore->eraseFromParent();

  return true;
}

static bool mergeConditionalStores(BranchInst *PBI, BranchInst *QBI,
                                   DomTreeUpdater *DTU, const DataLayout &DL,
                                   const TargetTransformInfo &TTI) {
  // The intention here is to find diamonds or triangles (see below) where each
  // conditional block contains a store to the same address. Both of these
  // stores are conditional, so they can't be unconditionally sunk. But it may
  // be profitable to speculatively sink the stores into one merged store at the
  // end, and predicate the merged store on the union of the two conditions of
  // PBI and QBI.
  //
  // This can reduce the number of stores executed if both of the conditions are
  // true, and can allow the blocks to become small enough to be if-converted.
  // This optimization will also chain, so that ladders of test-and-set
  // sequences can be if-converted away.
  //
  // We only deal with simple diamonds or triangles:
  //
  //     PBI       or      PBI        or a combination of the two
  //    /   \               | \
  //   PTB  PFB             |  PFB
  //    \   /               | /
  //     QBI                QBI
  //    /  \                | \
  //   QTB  QFB             |  QFB
  //    \  /                | /
  //    PostBB            PostBB
  //
  // We model triangles as a type of diamond with a nullptr "true" block.
  // Triangles are canonicalized so that the fallthrough edge is represented by
  // a true condition, as in the diagram above.
  BasicBlock *PTB = PBI->getSuccessor(0);
  BasicBlock *PFB = PBI->getSuccessor(1);
  BasicBlock *QTB = QBI->getSuccessor(0);
  BasicBlock *QFB = QBI->getSuccessor(1);
  BasicBlock *PostBB = QFB->getSingleSuccessor();

  // Make sure we have a good guess for PostBB. If QTB's only successor is
  // QFB, then QFB is a better PostBB.
  if (QTB->getSingleSuccessor() == QFB)
    PostBB = QFB;

  // If we couldn't find a good PostBB, stop.
  if (!PostBB)
    return false;

  bool InvertPCond = false, InvertQCond = false;
  // Canonicalize fallthroughs to the true branches.
  if (PFB == QBI->getParent()) {
    std::swap(PFB, PTB);
    InvertPCond = true;
  }
  if (QFB == PostBB) {
    std::swap(QFB, QTB);
    InvertQCond = true;
  }

  // From this point on we can assume PTB or QTB may be fallthroughs but PFB
  // and QFB may not. Model fallthroughs as a nullptr block.
  if (PTB == QBI->getParent())
    PTB = nullptr;
  if (QTB == PostBB)
    QTB = nullptr;

  // Legality bailouts. We must have at least the non-fallthrough blocks and
  // the post-dominating block, and the non-fallthroughs must only have one
  // predecessor.
  auto HasOnePredAndOneSucc = [](BasicBlock *BB, BasicBlock *P, BasicBlock *S) {
    return BB->getSinglePredecessor() == P && BB->getSingleSuccessor() == S;
  };
  if (!HasOnePredAndOneSucc(PFB, PBI->getParent(), QBI->getParent()) ||
      !HasOnePredAndOneSucc(QFB, QBI->getParent(), PostBB))
    return false;
  if ((PTB && !HasOnePredAndOneSucc(PTB, PBI->getParent(), QBI->getParent())) ||
      (QTB && !HasOnePredAndOneSucc(QTB, QBI->getParent(), PostBB)))
    return false;
  if (!QBI->getParent()->hasNUses(2))
    return false;

  // OK, this is a sequence of two diamonds or triangles.
  // Check if there are stores in PTB or PFB that are repeated in QTB or QFB.
  SmallPtrSet<Value *, 4> PStoreAddresses, QStoreAddresses;
  for (auto *BB : {PTB, PFB}) {
    if (!BB)
      continue;
    for (auto &I : *BB)
      if (StoreInst *SI = dyn_cast<StoreInst>(&I))
        PStoreAddresses.insert(SI->getPointerOperand());
  }
  for (auto *BB : {QTB, QFB}) {
    if (!BB)
      continue;
    for (auto &I : *BB)
      if (StoreInst *SI = dyn_cast<StoreInst>(&I))
        QStoreAddresses.insert(SI->getPointerOperand());
  }

  set_intersect(PStoreAddresses, QStoreAddresses);
  // set_intersect mutates PStoreAddresses in place. Rename it here to make it
  // clear what it contains.
  auto &CommonAddresses = PStoreAddresses;

  bool Changed = false;
  for (auto *Address : CommonAddresses)
    Changed |=
        mergeConditionalStoreToAddress(PTB, PFB, QTB, QFB, PostBB, Address,
                                       InvertPCond, InvertQCond, DTU, DL, TTI);
  return Changed;
}

/// If the previous block ended with a widenable branch, determine if reusing
/// the target block is profitable and legal.  This will have the effect of
/// "widening" PBI, but doesn't require us to reason about hosting safety.
static bool tryWidenCondBranchToCondBranch(BranchInst *PBI, BranchInst *BI,
                                           DomTreeUpdater *DTU) {
  // TODO: This can be generalized in two important ways:
  // 1) We can allow phi nodes in IfFalseBB and simply reuse all the input
  //    values from the PBI edge.
  // 2) We can sink side effecting instructions into BI's fallthrough
  //    successor provided they doesn't contribute to computation of
  //    BI's condition.
  BasicBlock *IfTrueBB = PBI->getSuccessor(0);
  BasicBlock *IfFalseBB = PBI->getSuccessor(1);
  if (!isWidenableBranch(PBI) || IfTrueBB != BI->getParent() ||
      !BI->getParent()->getSinglePredecessor())
    return false;
  if (!IfFalseBB->phis().empty())
    return false; // TODO
  // This helps avoid infinite loop with SimplifyCondBranchToCondBranch which
  // may undo the transform done here.
  // TODO: There might be a more fine-grained solution to this.
  if (!llvm::succ_empty(IfFalseBB))
    return false;
  // Use lambda to lazily compute expensive condition after cheap ones.
  auto NoSideEffects = [](BasicBlock &BB) {
    return llvm::none_of(BB, [](const Instruction &I) {
        return I.mayWriteToMemory() || I.mayHaveSideEffects();
      });
  };
  if (BI->getSuccessor(1) != IfFalseBB && // no inf looping
      BI->getSuccessor(1)->getTerminatingDeoptimizeCall() && // profitability
      NoSideEffects(*BI->getParent())) {
    auto *OldSuccessor = BI->getSuccessor(1);
    OldSuccessor->removePredecessor(BI->getParent());
    BI->setSuccessor(1, IfFalseBB);
    if (DTU)
      DTU->applyUpdates(
          {{DominatorTree::Insert, BI->getParent(), IfFalseBB},
           {DominatorTree::Delete, BI->getParent(), OldSuccessor}});
    return true;
  }
  if (BI->getSuccessor(0) != IfFalseBB && // no inf looping
      BI->getSuccessor(0)->getTerminatingDeoptimizeCall() && // profitability
      NoSideEffects(*BI->getParent())) {
    auto *OldSuccessor = BI->getSuccessor(0);
    OldSuccessor->removePredecessor(BI->getParent());
    BI->setSuccessor(0, IfFalseBB);
    if (DTU)
      DTU->applyUpdates(
          {{DominatorTree::Insert, BI->getParent(), IfFalseBB},
           {DominatorTree::Delete, BI->getParent(), OldSuccessor}});
    return true;
  }
  return false;
}

/// If we have a conditional branch as a predecessor of another block,
/// this function tries to simplify it.  We know
/// that PBI and BI are both conditional branches, and BI is in one of the
/// successor blocks of PBI - PBI branches to BI.
bool SimplifyCondBranchToCondBranch(BranchInst *PBI, BranchInst *BI,
                                           DomTreeUpdater *DTU,
                                           const DataLayout &DL,
                                           const TargetTransformInfo &TTI) {
  assert(PBI->isConditional() && BI->isConditional());
  BasicBlock *BB = BI->getParent();

  // If this block ends with a branch instruction, and if there is a
  // predecessor that ends on a branch of the same condition, make
  // this conditional branch redundant.
  if (PBI->getCondition() == BI->getCondition() &&
      PBI->getSuccessor(0) != PBI->getSuccessor(1)) {
    // Okay, the outcome of this conditional branch is statically
    // knowable.  If this block had a single pred, handle specially, otherwise
    // FoldCondBranchOnValueKnownInPredecessor() will handle it.
    if (BB->getSinglePredecessor()) {
      // Turn this into a branch on constant.
      bool CondIsTrue = PBI->getSuccessor(0) == BB;
      BI->setCondition(
          ConstantInt::get(Type::getInt1Ty(BB->getContext()), CondIsTrue));
      return true; // Nuke the branch on constant.
    }
  }

  // If the previous block ended with a widenable branch, determine if reusing
  // the target block is profitable and legal.  This will have the effect of
  // "widening" PBI, but doesn't require us to reason about hosting safety.
  if (tryWidenCondBranchToCondBranch(PBI, BI, DTU))
    return true;

  // If both branches are conditional and both contain stores to the same
  // address, remove the stores from the conditionals and create a conditional
  // merged store at the end.
  if (MergeCondStores && mergeConditionalStores(PBI, BI, DTU, DL, TTI))
    return true;

  // If this is a conditional branch in an empty block, and if any
  // predecessors are a conditional branch to one of our destinations,
  // fold the conditions into logical ops and one cond br.

  // Ignore dbg intrinsics.
  if (&*BB->instructionsWithoutDebug(false).begin() != BI)
    return false;

  int PBIOp, BIOp;
  if (PBI->getSuccessor(0) == BI->getSuccessor(0)) {
    PBIOp = 0;
    BIOp = 0;
  } else if (PBI->getSuccessor(0) == BI->getSuccessor(1)) {
    PBIOp = 0;
    BIOp = 1;
  } else if (PBI->getSuccessor(1) == BI->getSuccessor(0)) {
    PBIOp = 1;
    BIOp = 0;
  } else if (PBI->getSuccessor(1) == BI->getSuccessor(1)) {
    PBIOp = 1;
    BIOp = 1;
  } else {
    return false;
  }

  // Check to make sure that the other destination of this branch
  // isn't BB itself.  If so, this is an infinite loop that will
  // keep getting unwound.
  if (PBI->getSuccessor(PBIOp) == BB)
    return false;

  // If predecessor's branch probability to BB is too low don't merge branches.
  SmallVector<uint32_t, 2> PredWeights;
  if (!PBI->getMetadata(LLVMContext::MD_unpredictable) &&
      extractBranchWeights(*PBI, PredWeights) &&
      (static_cast<uint64_t>(PredWeights[0]) + PredWeights[1]) != 0) {

    BranchProbability CommonDestProb = BranchProbability::getBranchProbability(
        PredWeights[PBIOp],
        static_cast<uint64_t>(PredWeights[0]) + PredWeights[1]);

    BranchProbability Likely = TTI.getPredictableBranchThreshold();
    if (CommonDestProb >= Likely)
      return false;
  }

  // Do not perform this transformation if it would require
  // insertion of a large number of select instructions. For targets
  // without predication/cmovs, this is a big pessimization.

  BasicBlock *CommonDest = PBI->getSuccessor(PBIOp);
  BasicBlock *RemovedDest = PBI->getSuccessor(PBIOp ^ 1);
  unsigned NumPhis = 0;
  for (BasicBlock::iterator II = CommonDest->begin(); isa<PHINode>(II);
       ++II, ++NumPhis) {
    if (NumPhis > 2) // Disable this xform.
      return false;
  }

  // Finally, if everything is ok, fold the branches to logical ops.
  BasicBlock *OtherDest = BI->getSuccessor(BIOp ^ 1);

  LLVM_DEBUG(dbgs() << "FOLDING BRs:" << *PBI->getParent()
                    << "AND: " << *BI->getParent());

  SmallVector<DominatorTree::UpdateType, 5> Updates;

  // If OtherDest *is* BB, then BB is a basic block with a single conditional
  // branch in it, where one edge (OtherDest) goes back to itself but the other
  // exits.  We don't *know* that the program avoids the infinite loop
  // (even though that seems likely).  If we do this xform naively, we'll end up
  // recursively unpeeling the loop.  Since we know that (after the xform is
  // done) that the block *is* infinite if reached, we just make it an obviously
  // infinite loop with no cond branch.
  if (OtherDest == BB) {
    // Insert it at the end of the function, because it's either code,
    // or it won't matter if it's hot. :)
    BasicBlock *InfLoopBlock =
        BasicBlock::Create(BB->getContext(), "infloop", BB->getParent());
    BranchInst::Create(InfLoopBlock, InfLoopBlock);
    if (DTU)
      Updates.push_back({DominatorTree::Insert, InfLoopBlock, InfLoopBlock});
    OtherDest = InfLoopBlock;
  }

  LLVM_DEBUG(dbgs() << *PBI->getParent()->getParent());

  // BI may have other predecessors.  Because of this, we leave
  // it alone, but modify PBI.

  // Make sure we get to CommonDest on True&True directions.
  Value *PBICond = PBI->getCondition();
  IRBuilder<NoFolder> Builder(PBI);
  if (PBIOp)
    PBICond = Builder.CreateNot(PBICond, PBICond->getName() + ".not");

  Value *BICond = BI->getCondition();
  if (BIOp)
    BICond = Builder.CreateNot(BICond, BICond->getName() + ".not");

  // Merge the conditions.
  Value *Cond =
      createLogicalOp(Builder, Instruction::Or, PBICond, BICond, "brmerge");

  // Modify PBI to branch on the new condition to the new dests.
  PBI->setCondition(Cond);
  PBI->setSuccessor(0, CommonDest);
  PBI->setSuccessor(1, OtherDest);

  // [hwtHls]
  // If BI was a loop latch, it may have had associated loop metadata.
  // We need to copy it to the new latch, that is, PBI.
  if (MDNode *LoopMD = BI->getMetadata(LLVMContext::MD_loop))
    PBI->setMetadata(LLVMContext::MD_loop, LoopMD);

  if (DTU) {
    Updates.push_back({DominatorTree::Insert, PBI->getParent(), OtherDest});
    Updates.push_back({DominatorTree::Delete, PBI->getParent(), RemovedDest});

    DTU->applyUpdates(Updates);
  }

  // Update branch weight for PBI.
  uint64_t PredTrueWeight, PredFalseWeight, SuccTrueWeight, SuccFalseWeight;
  uint64_t PredCommon, PredOther, SuccCommon, SuccOther;
  bool HasWeights =
      extractPredSuccWeights(PBI, BI, PredTrueWeight, PredFalseWeight,
                             SuccTrueWeight, SuccFalseWeight);
  if (HasWeights) {
    PredCommon = PBIOp ? PredFalseWeight : PredTrueWeight;
    PredOther = PBIOp ? PredTrueWeight : PredFalseWeight;
    SuccCommon = BIOp ? SuccFalseWeight : SuccTrueWeight;
    SuccOther = BIOp ? SuccTrueWeight : SuccFalseWeight;
    // The weight to CommonDest should be PredCommon * SuccTotal +
    //                                    PredOther * SuccCommon.
    // The weight to OtherDest should be PredOther * SuccOther.
    uint64_t NewWeights[2] = {PredCommon * (SuccCommon + SuccOther) +
                                  PredOther * SuccCommon,
                              PredOther * SuccOther};
    // Halve the weights if any of them cannot fit in an uint32_t
    FitWeights(NewWeights);

    setBranchWeights(PBI, NewWeights[0], NewWeights[1]);
  }

  // OtherDest may have phi nodes.  If so, add an entry from PBI's
  // block that are identical to the entries for BI's block.
  AddPredecessorToBlock(OtherDest, PBI->getParent(), BB);

  // We know that the CommonDest already had an edge from PBI to
  // it.  If it has PHIs though, the PHIs may have different
  // entries for BB and PBI's BB.  If so, insert a select to make
  // them agree.
  for (PHINode &PN : CommonDest->phis()) {
    Value *BIV = PN.getIncomingValueForBlock(BB);
    unsigned PBBIdx = PN.getBasicBlockIndex(PBI->getParent());
    Value *PBIV = PN.getIncomingValue(PBBIdx);
    if (BIV != PBIV) {
      // Insert a select in PBI to pick the right value.
      SelectInst *NV = cast<SelectInst>(
          Builder.CreateSelect(PBICond, PBIV, BIV, PBIV->getName() + ".mux"));
      PN.setIncomingValue(PBBIdx, NV);
      // Although the select has the same condition as PBI, the original branch
      // weights for PBI do not apply to the new select because the select's
      // 'logical' edges are incoming edges of the phi that is eliminated, not
      // the outgoing edges of PBI.
      if (HasWeights) {
        uint64_t PredCommon = PBIOp ? PredFalseWeight : PredTrueWeight;
        uint64_t PredOther = PBIOp ? PredTrueWeight : PredFalseWeight;
        uint64_t SuccCommon = BIOp ? SuccFalseWeight : SuccTrueWeight;
        uint64_t SuccOther = BIOp ? SuccTrueWeight : SuccFalseWeight;
        // The weight to PredCommonDest should be PredCommon * SuccTotal.
        // The weight to PredOtherDest should be PredOther * SuccCommon.
        uint64_t NewWeights[2] = {PredCommon * (SuccCommon + SuccOther),
                                  PredOther * SuccCommon};

        FitWeights(NewWeights);

        setBranchWeights(NV, NewWeights[0], NewWeights[1]);
      }
    }
  }

  LLVM_DEBUG(dbgs() << "INTO: " << *PBI->getParent());
  LLVM_DEBUG(dbgs() << *PBI->getParent()->getParent());

  // This basic block is probably dead.  We know it has at least
  // one fewer predecessor.
  return true;
}

}
