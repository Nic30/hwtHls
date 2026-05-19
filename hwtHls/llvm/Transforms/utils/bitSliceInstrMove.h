#include <llvm/IR/Instruction.h>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

// BitRangeGet and TruncInst are implementation of bitvector slice, in order to
// reduce code replication these instructions are always kept directly after src
// operand (or after phis if src is a PHINode) this instructions moves slices
// which are not in slice list directly after src operand
bool moveIntoSliceSuccessorsOf(llvm::Instruction &IToMoveAfterSrc,
							   llvm::Instruction &src);

bool BitRangeGetMoveIntoSliceSuccessorsOfSrcOperand(llvm::CallInst &I);
bool TruncInstMoveIntoSliceSuccessorsOfSrcOperand(llvm::TruncInst &I);
void moveSlicesDirectlyAfterSrcOpDef(llvm::Function &F);
}