#pragma once

#include <map>

#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/LoopInfo.h>

#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/mergeSets.h>

// Efficient liveness computation using merge sets and DJ-graphs
// https://dl.acm.org/doi/10.1145/2086696.2086706
// based on
// https://github.com/ethanblake4/control_flow_graph/blob/main/lib/src/liveness.dart
// https://github.com/SchrodingerZhu/domtree/blob/main/src/djgraph.rs
// :note: similar to llvm/CodeGen/RDFLiveness.h but for IR (instead of MIR)
// :note: Naive implementations do not scale.
//   https://github.com/adava/LLVM-Liveness-Analysis/blob/master/Pass/Transforms/LV/Liveness.cpp
//   https://github.com/dantengknight/llvm-liveness-analysis-pass/blob/master/Liveness/Liveness.cpp 
namespace hwtHls {

// :attention: the  allLiveInUsingMergeSet/computeAllLiveins does not support the CFG
//      with duplicit edge between blocks. Such jump edges may appear for example with SwitchInst
//      which have multiple cases jumping to the same block.
//      (use fixDublicitCfgEdgesByNewBBInsertion before)
std::map<llvm::BasicBlock *, llvm::SetVector<llvm::Instruction *>>
allLiveInUsingMergeSet(llvm::BasicBlock &root,
					   const llvm::DominatorTree &dominators,
					   const MergeSets &mergeSets);
std::map<llvm::BasicBlock *, llvm::SetVector<llvm::Instruction *>>
computeAllLiveins(llvm::Function &F, llvm::DominatorTree &DT);

bool fixDublicitCfgEdgesByNewBBInsertion(llvm::DomTreeUpdater * DTU, llvm::LoopInfo * LI, llvm::Function & F);
}
