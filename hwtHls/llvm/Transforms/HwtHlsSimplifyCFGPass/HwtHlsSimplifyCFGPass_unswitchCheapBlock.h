#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/BasicBlock.h>

namespace hwtHls {

/// Unswitch a phi-only block BB0 with multiple predecessors and a single
/// successor which has multiple predecessors.
/// * The predecessors of BB0 and S may have all duplicated values.
/// * The BB0 must not be a latch.
/// * Phis in BB0 should not have use outside of S by the definition of SSA.
///
/// Transformation:
/// - Let S = BB0.getSingleSuccessor().
/// - Keep BB0 for the last predecessor.
/// - For each other predecessor Pi, create an empty BB0.i of BB0 (with 'br S'),
///   and redirect Pi to branch to BB0.i instead.
/// - Sink BB0 phi operands into S with updated predecessor to be copies of BB0
///
/// Returns true if any transformation was applied.
/// .. code-block:: llvm
///     ; original
/// 	P0:
/// 	   br label %BB0
/// 	P1:
/// 	   br label %BB0
/// 	P2:
/// 	   br label %S
/// 	BB0:
/// 	   %phi0 = phi i8 [0, %P0 ], [1, %P1 ]
/// 	   br label %S
/// 	S:
/// 	   %phi1 = phi i8 [%phi0, %BB0 ], [2, %P2 ]
/// 
/// 	; transformed
/// 	P0:
/// 	   br label %BB0.0
/// 	P1:
/// 	   br label %BB0.1
/// 	P2:
/// 	   br label %S
/// 	BB0.0:
/// 	   br label %S
/// 	BB0.1:
/// 	   br label %S
/// 	S:
/// 	   %phi1 = phi i8 [0, %BB0.0 ],  [1, %BB0.1 ], [2, %P2 ]

bool HwtHlsSimplifyCFGPass_unswitchCheapBlock(llvm::DomTreeUpdater &DTU,
											  llvm::BasicBlock &BB0);

}