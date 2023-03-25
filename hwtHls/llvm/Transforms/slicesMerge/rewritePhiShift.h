#pragma once
#include <llvm/IR/BasicBlock.h>
#include "utils.h"

namespace hwtHls {

/*
 * Rewrite chained PHIs as a phi of shifted values
 *
 * bb0:
 *    %1 = phi i1 [ %2, %bb0 ], [ false, %bb1 ],  ...
 *    %2 = phi i1 [ %3, %bb0 ], [ false, %bb1 ],  ...
 *    %3 = phi i1 [ true, %bb0 ], [ false, %bb1 ],  ...
 *    br i1 %3, label bb0, label bb1
 * bb1:
 *    br label bb0
 *
 * to
 *
 * bb0:
 *  %"1,2,3" = phi i3 [%"bb0:1,2,3", %bb0], [i3 0, %bb1], ...
 *  %1 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.0(i3 %"1,2,3", i64 0)
 *  %2 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.1(i3 %"1,2,3", i64 1)
 *  %3 = call i1 @hwtHls.bitRangeGet.i3.i64.i1.2(i3 %"1,2,3", i64 2)
 *  %"shiftPhi<1,2,3>" = call i3 @hwtHls.bitConcat.i1.i1.i1(%1, %2, true)
 *  br i1 %3, label bb0, label bb1
 * bb1:
 *    br label bb0
 *
 *
 * collect PHIs which are chained
 * * PHIs may implement multiple shifts and non shift operations at once
 *   we must extract all PHIs which are chained together because
 *   bitRangeGet and concat can not be inserted between PHIs
 * */
bool phiShiftPatternRewrite(llvm::BasicBlock &BB, const CreateBitRangeGetFn & createSlice);

/*
 * Create one wider PHINode from group of phis
 * */
llvm::PHINode* mergePhisToWiderPhi(llvm::LLVMContext & C, const std::string &nameStem,
		const std::vector<llvm::PHINode*> &phis);

}
