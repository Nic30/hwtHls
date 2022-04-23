#pragma once

#include <llvm/ADT/APInt.h>
#include <llvm/ADT/ArrayRef.h>
#include <llvm/ADT/DenseMap.h>
#include <llvm/ADT/MapVector.h>
#include <llvm/ADT/PointerIntPair.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/Analysis/BlockFrequencyInfo.h>
#include <llvm/Analysis/BranchProbabilityInfo.h>
#include <llvm/Analysis/ConstantFolding.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/MemoryBuiltins.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/VectorUtils.h>
#include <llvm/CodeGen/Analysis.h>
#include <llvm/CodeGen/ISDOpcodes.h>
#include <llvm/CodeGen/SelectionDAGNodes.h>
#include <llvm/CodeGen/TargetLowering.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/ValueTypes.h>
#include <llvm/IR/Argument.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Constant.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DataLayout.h>
#include <llvm/IR/DebugInfo.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/GetElementPtrTypeIterator.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/IR/GlobalVariable.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/InlineAsm.h>
#include <llvm/IR/InstrTypes.h>
#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IntrinsicInst.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/MDBuilder.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Operator.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/IR/Statepoint.h>
#include <llvm/IR/Type.h>
#include <llvm/IR/Use.h>
#include <llvm/IR/User.h>
#include <llvm/IR/Value.h>
#include <llvm/IR/ValueHandle.h>
#include <llvm/IR/ValueMap.h>
#include <llvm/InitializePasses.h>
#include <llvm/Pass.h>
#include <llvm/Support/BlockFrequency.h>
#include <llvm/Support/BranchProbability.h>
#include <llvm/Support/Casting.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/Compiler.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Support/MachineValueType.h>
#include <llvm/Support/MathExtras.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/Target/TargetOptions.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/BypassSlowDivision.h>
#include <llvm/Transforms/Utils/Local.h>
#include <llvm/Transforms/Utils/SimplifyLibCalls.h>
#include <llvm/Transforms/Utils/SizeOpts.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iterator>
#include <limits>
#include <memory>
#include <utility>
#include <vector>

namespace hwtHls {

namespace llvmSrc {

enum ExtType {
  ZeroExtension,   // Zero extension has been seen.
  SignExtension,   // Sign extension has been seen.
  BothExtension    // This extension type is used if we saw sext after
                   // ZeroExtension had been set, or if we saw zext after
                   // SignExtension had been set. It makes the type
                   // information of a promoted instruction invalid.
};

using SetOfInstrs = llvm::SmallPtrSet<llvm::Instruction *, 16>;
using TypeIsSExt = llvm::PointerIntPair<llvm::Type *, 2, ExtType>;
using InstrToOrigTy = llvm::DenseMap<llvm::Instruction *, TypeIsSExt>;
using SExts = llvm::SmallVector<llvm::Instruction *, 16>;
using ValueToSExts = llvm::DenseMap<llvm::Value *, SExts>;

class TypePromotionTransaction;

/// Transform the code to expose more pattern
/// matching during instruction selection.
  class CodeGenPrepare : public llvm::FunctionPass {
    const llvm::TargetMachine *TM = nullptr;
    const llvm::TargetSubtargetInfo *SubtargetInfo;
    const llvm::TargetLowering *TLI = nullptr;
    const llvm::TargetRegisterInfo *TRI;
    const llvm::TargetTransformInfo *TTI = nullptr;
    const llvm::TargetLibraryInfo *TLInfo;
    const llvm::LoopInfo *LI;
    std::unique_ptr<llvm::BlockFrequencyInfo> BFI;
    std::unique_ptr<llvm::BranchProbabilityInfo> BPI;
    llvm::ProfileSummaryInfo *PSI;

    /// As we scan instructions optimizing them, this is the next instruction
    /// to optimize. Transforms that can invalidate this should update it.
    llvm::BasicBlock::iterator CurInstIterator;

    /// Keeps track of non-local addresses that have been sunk into a block.
    /// This allows us to avoid inserting duplicate code for blocks with
    /// multiple load/stores of the same address. The usage of WeakTrackingVH
    /// enables SunkAddrs to be treated as a cache whose entries can be
    /// invalidated if a sunken address computation has been erased.
    llvm::ValueMap<llvm::Value*, llvm::WeakTrackingVH> SunkAddrs;

    /// Keeps track of all instructions inserted for the current function.
    SetOfInstrs InsertedInsts;

    /// Keeps track of the type of the related instruction before their
    /// promotion for the current function.
    InstrToOrigTy PromotedInsts;

    /// Keep track of instructions removed during promotion.
    SetOfInstrs RemovedInsts;

    /// Keep track of sext chains based on their initial value.
    llvm::DenseMap<llvm::Value *, llvm::Instruction *> SeenChainsForSExt;

    /// Keep track of GEPs accessing the same data structures such as structs or
    /// arrays that are candidates to be split later because of their large
    /// size.
    llvm::MapVector<
        llvm::AssertingVH<llvm::Value>,
        llvm::SmallVector<std::pair<llvm::AssertingVH<llvm::GetElementPtrInst>, int64_t>, 32>>
        LargeOffsetGEPMap;

    /// Keep track of new GEP base after splitting the GEPs having large offset.
    llvm::SmallSet<llvm::AssertingVH<llvm::Value>, 2> NewGEPBases;

    /// Map serial numbers to Large offset GEPs.
    llvm::DenseMap<llvm::AssertingVH<llvm::GetElementPtrInst>, int> LargeOffsetGEPID;

    /// Keep track of SExt promoted.
    ValueToSExts ValToSExtendedUses;

    /// True if the function has the OptSize attribute.
    bool OptSize;

    /// DataLayout for the Function being processed.
    const llvm::DataLayout *DL = nullptr;

    /// Building the dominator tree can be expensive, so we only build it
    /// lazily and update it when required.
    std::unique_ptr<llvm::DominatorTree> DT;

  public:
    static char ID; // Pass identification, replacement for typeid

    CodeGenPrepare();
    bool runOnFunction(llvm::Function &F) override;

    llvm::StringRef getPassName() const override { return "CodeGen Prepare"; }

    void getAnalysisUsage(llvm::AnalysisUsage &AU) const override {
      // FIXME: When we can selectively preserve passes, preserve the domtree.
      AU.addRequired<llvm::ProfileSummaryInfoWrapperPass>();
      AU.addRequired<llvm::TargetLibraryInfoWrapperPass>();
      AU.addRequired<llvm::TargetPassConfig>();
      AU.addRequired<llvm::TargetTransformInfoWrapperPass>();
      AU.addRequired<llvm::LoopInfoWrapperPass>();
    }

  private:
    template <typename F>
    void resetIteratorIfInvalidatedWhileCalling(llvm::BasicBlock *BB, F f) {
      // Substituting can cause recursive simplifications, which can invalidate
      // our iterator.  Use a WeakTrackingVH to hold onto it in case this
      // happens.
      llvm::Value *CurValue = &*CurInstIterator;
      llvm::WeakTrackingVH IterHandle(CurValue);

      f();

      // If the iterator instruction was recursively deleted, start over at the
      // start of the block.
      if (IterHandle != CurValue) {
        CurInstIterator = BB->begin();
        SunkAddrs.clear();
      }
    }

    // Get the DominatorTree, building if necessary.
    llvm::DominatorTree &getDT(llvm::Function &F) {
      if (!DT)
        DT = std::make_unique<llvm::DominatorTree>(F);
      return *DT;
    }

    void removeAllAssertingVHReferences(llvm::Value *V);
    bool eliminateAssumptions(llvm::Function &F);
    bool eliminateFallThrough(llvm::Function &F);
    bool eliminateMostlyEmptyBlocks(llvm::Function &F);
    llvm::BasicBlock *findDestBlockOfMergeableEmptyBlock(llvm::BasicBlock *BB);
    bool canMergeBlocks(const llvm::BasicBlock *BB, const llvm::BasicBlock *DestBB) const;
    void eliminateMostlyEmptyBlock(llvm::BasicBlock *BB);
    bool isMergingEmptyBlockProfitable(llvm::BasicBlock *BB, llvm::BasicBlock *DestBB,
                                       bool isPreheader);
    bool makeBitReverse(llvm::Instruction &I);
    bool optimizeBlock(llvm::BasicBlock &BB, bool &ModifiedDT);
    bool optimizeInst(llvm::Instruction *I, bool &ModifiedDT);
    bool optimizeMemoryInst(llvm::Instruction *MemoryInst, llvm::Value *Addr,
    		llvm::Type *AccessTy, unsigned AddrSpace);
    bool optimizeGatherScatterInst(llvm::Instruction *MemoryInst, llvm::Value *Ptr);
    bool optimizeInlineAsmInst(llvm::CallInst *CS);
    bool optimizeCallInst(llvm::CallInst *CI, bool &ModifiedDT);
    bool optimizeExt(llvm::Instruction *&I);
    bool optimizeExtUses(llvm::Instruction *I);
    virtual bool optimizeLoadExt(llvm::LoadInst *Load);
    bool optimizeShiftInst(llvm::BinaryOperator *BO);
    bool optimizeFunnelShift(llvm::IntrinsicInst *Fsh);
    bool optimizeSelectInst(llvm::SelectInst *SI);
    bool optimizeShuffleVectorInst(llvm::ShuffleVectorInst *SVI);
    virtual bool optimizeSwitchInst(llvm::SwitchInst *SI);
    bool optimizeExtractElementInst(llvm::Instruction *Inst);
    bool dupRetToEnableTailCallOpts(llvm::BasicBlock *BB, bool &ModifiedDT);
    bool fixupDbgValue(llvm::Instruction *I);
    bool placeDbgValues(llvm::Function &F);
    bool placePseudoProbes(llvm::Function &F);
    bool canFormExtLd(const llvm::SmallVectorImpl<llvm::Instruction *> &MovedExts,
    		llvm::LoadInst *&LI, llvm::Instruction *&Inst, bool HasPromoted);
    bool tryToPromoteExts(TypePromotionTransaction &TPT,
                          const llvm::SmallVectorImpl<llvm::Instruction *> &Exts,
						  llvm::SmallVectorImpl<llvm::Instruction *> &ProfitablyMovedExts,
                          unsigned CreatedInstsCost = 0);
    bool mergeSExts(llvm::Function &F);
    bool splitLargeGEPOffsets();
    bool optimizePhiType(llvm::PHINode *Inst, llvm::SmallPtrSetImpl<llvm::PHINode *> &Visited,
                         llvm::SmallPtrSetImpl<llvm::Instruction *> &DeletedInstrs);
    bool optimizePhiTypes(llvm::Function &F);
    bool performAddressTypePromotion(
    		llvm::Instruction *&Inst,
        bool AllowPromotionWithoutCommonHeader,
        bool HasPromoted, TypePromotionTransaction &TPT,
		llvm::SmallVectorImpl<llvm::Instruction *> &SpeculativelyMovedExts);
    bool splitBranchCondition(llvm::Function &F, bool &ModifiedDT);
    bool simplifyOffsetableRelocate(llvm::GCStatepointInst &I);

    bool tryToSinkFreeOperands(llvm::Instruction *I);
    bool replaceMathCmpWithIntrinsic(llvm::BinaryOperator *BO, llvm::Value *Arg0,
    		llvm::Value *Arg1, llvm::CmpInst *Cmp,
			llvm::Intrinsic::ID IID);
    bool optimizeCmp(llvm::CmpInst *Cmp, bool &ModifiedDT);
    bool combineToUSubWithOverflow(llvm::CmpInst *Cmp, bool &ModifiedDT);
    bool combineToUAddWithOverflow(llvm::CmpInst *Cmp, bool &ModifiedDT);
    void verifyBFIUpdates(llvm::Function &F);
  };

} // end anonymous namespace


}
