#include <hwtHls/llvm/llvmSrc/LoopPeel.h>

#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/LoopIterator.h>
#include <llvm/IR/ProfDataUtils.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/ValueMapper.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/Support/Debug.h>

using namespace llvm;

#define DEBUG_TYPE "hwtHls-loop-peel"

STATISTIC(NumHwtHlsPeeled, "Number of loops peeled by hwtHls_peelLoop");

namespace hwtHls {
static const char *PeeledCountMetaData = "llvm.loop.peeled.count";
// :note: copied 1:1 from llvm-18 because use in hwtHls_peelLoop which is just peelLoop which exports peeled loop headers

struct WeightInfo {
  // Weights for current iteration.
  SmallVector<uint32_t> Weights;
  // Weights to subtract after each iteration.
  const SmallVector<uint32_t> SubWeights;
};

/// Update the branch weights of an exiting block of a peeled-off loop
/// iteration.
/// Let F is a weight of the edge to continue (fallthrough) into the loop.
/// Let E is a weight of the edge to an exit.
/// F/(F+E) is a probability to go to loop and E/(F+E) is a probability to
/// go to exit.
/// Then, Estimated ExitCount = F / E.
/// For I-th (counting from 0) peeled off iteration we set the weights for
/// the peeled exit as (EC - I, 1). It gives us reasonable distribution,
/// The probability to go to exit 1/(EC-I) increases. At the same time
/// the estimated exit count in the remainder loop reduces by I.
/// To avoid dealing with division rounding we can just multiple both part
/// of weights to E and use weight as (F - I * E, E).
static void updateBranchWeights(Instruction *Term, WeightInfo &Info) {
  setBranchWeights(*Term, Info.Weights);
  for (auto [Idx, SubWeight] : enumerate(Info.SubWeights))
    if (SubWeight != 0)
      // Don't set the probability of taking the edge from latch to loop header
      // to less than 1:1 ratio (meaning Weight should not be lower than
      // SubWeight), as this could significantly reduce the loop's hotness,
      // which would be incorrect in the case of underestimating the trip count.
      Info.Weights[Idx] =
          Info.Weights[Idx] > SubWeight
              ? std::max(Info.Weights[Idx] - SubWeight, SubWeight)
              : SubWeight;
}

/// Initialize the weights for all exiting blocks.
static void initBranchWeights(DenseMap<Instruction *, WeightInfo> &WeightInfos,
                              Loop *L) {
  SmallVector<BasicBlock *> ExitingBlocks;
  L->getExitingBlocks(ExitingBlocks);
  for (BasicBlock *ExitingBlock : ExitingBlocks) {
    Instruction *Term = ExitingBlock->getTerminator();
    SmallVector<uint32_t> Weights;
    if (!extractBranchWeights(*Term, Weights))
      continue;

    // See the comment on updateBranchWeights() for an explanation of what we
    // do here.
    uint32_t FallThroughWeights = 0;
    uint32_t ExitWeights = 0;
    for (auto [Succ, Weight] : zip(successors(Term), Weights)) {
      if (L->contains(Succ))
        FallThroughWeights += Weight;
      else
        ExitWeights += Weight;
    }

    // Don't try to update weights for degenerate case.
    if (FallThroughWeights == 0)
      continue;

    SmallVector<uint32_t> SubWeights;
    for (auto [Succ, Weight] : zip(successors(Term), Weights)) {
      if (!L->contains(Succ)) {
        // Exit weights stay the same.
        SubWeights.push_back(0);
        continue;
      }

      // Subtract exit weights on each iteration, distributed across all
      // fallthrough edges.
      double W = (double)Weight / (double)FallThroughWeights;
      SubWeights.push_back((uint32_t)(ExitWeights * W));
    }

    WeightInfos.insert({Term, {std::move(Weights), std::move(SubWeights)}});
  }
}

/// Clones the body of the loop L, putting it between \p InsertTop and \p
/// InsertBot.
/// \param IterNumber The serial number of the iteration currently being
/// peeled off.
/// \param ExitEdges The exit edges of the original loop.
/// \param[out] NewBlocks A list of the blocks in the newly created clone
/// \param[out] VMap The value map between the loop and the new clone.
/// \param LoopBlocks A helper for DFS-traversal of the loop.
/// \param LVMap A value-map that maps instructions from the original loop to
/// instructions in the last peeled-off iteration.
static void cloneLoopBlocks(
    Loop *L, unsigned IterNumber, BasicBlock *InsertTop, BasicBlock *InsertBot,
    SmallVectorImpl<std::pair<BasicBlock *, BasicBlock *>> &ExitEdges,
    SmallVectorImpl<BasicBlock *> &NewBlocks, LoopBlocksDFS &LoopBlocks,
    ValueToValueMapTy &VMap, ValueToValueMapTy &LVMap, DominatorTree *DT,
    LoopInfo *LI, ArrayRef<MDNode *> LoopLocalNoAliasDeclScopes,
    ScalarEvolution &SE) {
  BasicBlock *Header = L->getHeader();
  BasicBlock *Latch = L->getLoopLatch();
  BasicBlock *PreHeader = L->getLoopPreheader();

  Function *F = Header->getParent();
  LoopBlocksDFS::RPOIterator BlockBegin = LoopBlocks.beginRPO();
  LoopBlocksDFS::RPOIterator BlockEnd = LoopBlocks.endRPO();
  Loop *ParentLoop = L->getParentLoop();

  // For each block in the original loop, create a new copy,
  // and update the value map with the newly created values.
  for (LoopBlocksDFS::RPOIterator BB = BlockBegin; BB != BlockEnd; ++BB) {
    BasicBlock *NewBB = CloneBasicBlock(*BB, VMap, ".peel", F);
    NewBlocks.push_back(NewBB);

    // If an original block is an immediate child of the loop L, its copy
    // is a child of a ParentLoop after peeling. If a block is a child of
    // a nested loop, it is handled in the cloneLoop() call below.
    if (ParentLoop && LI->getLoopFor(*BB) == L)
      ParentLoop->addBasicBlockToLoop(NewBB, *LI);

    VMap[*BB] = NewBB;

    // If dominator tree is available, insert nodes to represent cloned blocks.
    if (DT) {
      if (Header == *BB)
        DT->addNewBlock(NewBB, InsertTop);
      else {
        DomTreeNode *IDom = DT->getNode(*BB)->getIDom();
        // VMap must contain entry for IDom, as the iteration order is RPO.
        DT->addNewBlock(NewBB, cast<BasicBlock>(VMap[IDom->getBlock()]));
      }
    }
  }

  {
    // Identify what other metadata depends on the cloned version. After
    // cloning, replace the metadata with the corrected version for both
    // memory instructions and noalias intrinsics.
    std::string Ext = (Twine("Peel") + Twine(IterNumber)).str();
    cloneAndAdaptNoAliasScopes(LoopLocalNoAliasDeclScopes, NewBlocks,
                               Header->getContext(), Ext);
  }

  // Recursively create the new Loop objects for nested loops, if any,
  // to preserve LoopInfo.
  for (Loop *ChildLoop : *L) {
    cloneLoop(ChildLoop, ParentLoop, VMap, LI, nullptr);
  }

  // Hook-up the control flow for the newly inserted blocks.
  // The new header is hooked up directly to the "top", which is either
  // the original loop preheader (for the first iteration) or the previous
  // iteration's exiting block (for every other iteration)
  InsertTop->getTerminator()->setSuccessor(0, cast<BasicBlock>(VMap[Header]));

  // Similarly, for the latch:
  // The original exiting edge is still hooked up to the loop exit.
  // The backedge now goes to the "bottom", which is either the loop's real
  // header (for the last peeled iteration) or the copied header of the next
  // iteration (for every other iteration)
  BasicBlock *NewLatch = cast<BasicBlock>(VMap[Latch]);
  auto *LatchTerm = cast<Instruction>(NewLatch->getTerminator());
  for (unsigned idx = 0, e = LatchTerm->getNumSuccessors(); idx < e; ++idx)
    if (LatchTerm->getSuccessor(idx) == Header) {
      LatchTerm->setSuccessor(idx, InsertBot);
      break;
    }
  if (DT)
    DT->changeImmediateDominator(InsertBot, NewLatch);

  // The new copy of the loop body starts with a bunch of PHI nodes
  // that pick an incoming value from either the preheader, or the previous
  // loop iteration. Since this copy is no longer part of the loop, we
  // resolve this statically:
  // For the first iteration, we use the value from the preheader directly.
  // For any other iteration, we replace the phi with the value generated by
  // the immediately preceding clone of the loop body (which represents
  // the previous iteration).
  for (BasicBlock::iterator I = Header->begin(); isa<PHINode>(I); ++I) {
    PHINode *NewPHI = cast<PHINode>(VMap[&*I]);
    if (IterNumber == 0) {
      VMap[&*I] = NewPHI->getIncomingValueForBlock(PreHeader);
    } else {
      Value *LatchVal = NewPHI->getIncomingValueForBlock(Latch);
      Instruction *LatchInst = dyn_cast<Instruction>(LatchVal);
      if (LatchInst && L->contains(LatchInst))
        VMap[&*I] = LVMap[LatchInst];
      else
        VMap[&*I] = LatchVal;
    }
    NewPHI->eraseFromParent();
  }

  // Fix up the outgoing values - we need to add a value for the iteration
  // we've just created. Note that this must happen *after* the incoming
  // values are adjusted, since the value going out of the latch may also be
  // a value coming into the header.
  for (auto Edge : ExitEdges)
    for (PHINode &PHI : Edge.second->phis()) {
      Value *LatchVal = PHI.getIncomingValueForBlock(Edge.first);
      Instruction *LatchInst = dyn_cast<Instruction>(LatchVal);
      if (LatchInst && L->contains(LatchInst))
        LatchVal = VMap[LatchVal];
      PHI.addIncoming(LatchVal, cast<BasicBlock>(VMap[Edge.first]));
      SE.forgetValue(&PHI);
    }

  // LastValueMap is updated with the values for the current loop
  // which are used the next time this function is called.
  for (auto KV : VMap)
    LVMap[KV.first] = KV.second;
}


/// Peel off the first \p PeelCount iterations of loop \p L.
///
/// Note that this does not peel them off as a single straight-line block.
/// Rather, each iteration is peeled off separately, and needs to check the
/// exit condition.
/// For loops that dynamically execute \p PeelCount iterations or less
/// this provides a benefit, since the peeled off iterations, which account
/// for the bulk of dynamic execution, can be further simplified by scalar
/// optimizations.
bool hwtHls_peelLoop(Loop *L, unsigned PeelCount, LoopInfo *LI,
                    ScalarEvolution *SE, DominatorTree &DT, AssumptionCache *AC,
                    bool PreserveLCSSA, ValueToValueMapTy &LVMap, SmallVector<BasicBlock*>& peeledHeaders) {
  assert(PeelCount > 0 && "Attempt to peel out zero iterations?");
  assert(canPeel(L) && "Attempt to peel a loop which is not peelable?");

  LoopBlocksDFS LoopBlocks(L);
  LoopBlocks.perform(LI);

  BasicBlock *Header = L->getHeader();
  BasicBlock *PreHeader = L->getLoopPreheader();
  BasicBlock *Latch = L->getLoopLatch();
  SmallVector<std::pair<BasicBlock *, BasicBlock *>, 4> ExitEdges;
  L->getExitEdges(ExitEdges);

  // Remember dominators of blocks we might reach through exits to change them
  // later. Immediate dominator of such block might change, because we add more
  // routes which can lead to the exit: we can reach it from the peeled
  // iterations too.
  DenseMap<BasicBlock *, BasicBlock *> NonLoopBlocksIDom;
  for (auto *BB : L->blocks()) {
    auto *BBDomNode = DT.getNode(BB);
    SmallVector<BasicBlock *, 16> ChildrenToUpdate;
    for (auto *ChildDomNode : BBDomNode->children()) {
      auto *ChildBB = ChildDomNode->getBlock();
      if (!L->contains(ChildBB))
        ChildrenToUpdate.push_back(ChildBB);
    }
    // The new idom of the block will be the nearest common dominator
    // of all copies of the previous idom. This is equivalent to the
    // nearest common dominator of the previous idom and the first latch,
    // which dominates all copies of the previous idom.
    BasicBlock *NewIDom = DT.findNearestCommonDominator(BB, Latch);
    for (auto *ChildBB : ChildrenToUpdate)
      NonLoopBlocksIDom[ChildBB] = NewIDom;
  }

  Function *F = Header->getParent();

  // Set up all the necessary basic blocks. It is convenient to split the
  // preheader into 3 parts - two blocks to anchor the peeled copy of the loop
  // body, and a new preheader for the "real" loop.

  // Peeling the first iteration transforms.
  //
  // PreHeader:
  // ...
  // Header:
  //   LoopBody
  //   If (cond) goto Header
  // Exit:
  //
  // into
  //
  // InsertTop:
  //   LoopBody
  //   If (!cond) goto Exit
  // InsertBot:
  // NewPreHeader:
  // ...
  // Header:
  //  LoopBody
  //  If (cond) goto Header
  // Exit:
  //
  // Each following iteration will split the current bottom anchor in two,
  // and put the new copy of the loop body between these two blocks. That is,
  // after peeling another iteration from the example above, we'll split
  // InsertBot, and get:
  //
  // InsertTop:
  //   LoopBody
  //   If (!cond) goto Exit
  // InsertBot:
  //   LoopBody
  //   If (!cond) goto Exit
  // InsertBot.next:
  // NewPreHeader:
  // ...
  // Header:
  //  LoopBody
  //  If (cond) goto Header
  // Exit:

  BasicBlock *InsertTop = SplitEdge(PreHeader, Header, &DT, LI);
  BasicBlock *InsertBot =
      SplitBlock(InsertTop, InsertTop->getTerminator(), &DT, LI);
  BasicBlock *NewPreHeader =
      SplitBlock(InsertBot, InsertBot->getTerminator(), &DT, LI);

  InsertTop->setName(Header->getName() + ".peel.begin");
  InsertBot->setName(Header->getName() + ".peel.next");
  NewPreHeader->setName(PreHeader->getName() + ".peel.newph");

  Instruction *LatchTerm =
      cast<Instruction>(cast<BasicBlock>(Latch)->getTerminator());

  // If we have branch weight information, we'll want to update it for the
  // newly created branches.
  DenseMap<Instruction *, WeightInfo> Weights;
  initBranchWeights(Weights, L);

  // Identify what noalias metadata is inside the loop: if it is inside the
  // loop, the associated metadata must be cloned for each iteration.
  SmallVector<MDNode *, 6> LoopLocalNoAliasDeclScopes;
  identifyNoAliasScopesToClone(L->getBlocks(), LoopLocalNoAliasDeclScopes);

  // For each peeled-off iteration, make a copy of the loop.
  for (unsigned Iter = 0; Iter < PeelCount; ++Iter) {
    SmallVector<BasicBlock *, 8> NewBlocks;
    ValueToValueMapTy VMap;

    cloneLoopBlocks(L, Iter, InsertTop, InsertBot, ExitEdges, NewBlocks,
                    LoopBlocks, VMap, LVMap, &DT, LI,
                    LoopLocalNoAliasDeclScopes, *SE);

    // Remap to use values from the current iteration instead of the
    // previous one.
    remapInstructionsInBlocks(NewBlocks, VMap);

    // Update IDoms of the blocks reachable through exits.
    if (Iter == 0)
      for (auto BBIDom : NonLoopBlocksIDom)
        DT.changeImmediateDominator(BBIDom.first,
                                     cast<BasicBlock>(LVMap[BBIDom.second]));
#ifdef EXPENSIVE_CHECKS
    assert(DT.verify(DominatorTree::VerificationLevel::Fast));
#endif

    for (auto &[Term, Info] : Weights) {
      auto *TermCopy = cast<Instruction>(VMap[Term]);
      updateBranchWeights(TermCopy, Info);
    }

    // Remove Loop metadata from the latch branch instruction
    // because it is not the Loop's latch branch anymore.
    auto *LatchTermCopy = cast<Instruction>(VMap[LatchTerm]);
    LatchTermCopy->setMetadata(LLVMContext::MD_loop, nullptr);

    InsertTop = InsertBot;
    InsertBot = SplitBlock(InsertBot, InsertBot->getTerminator(), &DT, LI);
    InsertBot->setName(Header->getName() + ".peel.next");

    F->splice(InsertTop->getIterator(), F, NewBlocks[0]->getIterator(),
              F->end());
    peeledHeaders.push_back(NewBlocks[0]);
  }

  // Now adjust the phi nodes in the loop header to get their initial values
  // from the last peeled-off iteration instead of the preheader.
  for (BasicBlock::iterator I = Header->begin(); isa<PHINode>(I); ++I) {
    PHINode *PHI = cast<PHINode>(I);
    Value *NewVal = PHI->getIncomingValueForBlock(Latch);
    Instruction *LatchInst = dyn_cast<Instruction>(NewVal);
    if (LatchInst && L->contains(LatchInst))
      NewVal = LVMap[LatchInst];

    PHI->setIncomingValueForBlock(NewPreHeader, NewVal);
  }

  for (const auto &[Term, Info] : Weights) {
    setBranchWeights(*Term, Info.Weights);
  }

  // Update Metadata for count of peeled off iterations.
  unsigned AlreadyPeeled = 0;
  if (auto Peeled = getOptionalIntLoopAttribute(L, PeeledCountMetaData))
    AlreadyPeeled = *Peeled;
  addStringMetadataToLoop(L, PeeledCountMetaData, AlreadyPeeled + PeelCount);

  if (Loop *ParentLoop = L->getParentLoop())
    L = ParentLoop;

  // We modified the loop, update SE.
  SE->forgetTopmostLoop(L);
  SE->forgetBlockAndLoopDispositions();

#ifdef EXPENSIVE_CHECKS
  // Finally DomtTree must be correct.
  assert(DT.verify(DominatorTree::VerificationLevel::Fast));
#endif

  // FIXME: Incrementally update loop-simplify
  // simplifyLoop(L, &DT, LI, SE, AC, nullptr, PreserveLCSSA);

  NumHwtHlsPeeled++;

  return true;
}
}
