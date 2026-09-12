#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

// reduce empty successor blocks after SwitchInst if there are <=2 unique exit blocks, no loop
// * the instruction which can be speculated should already be hoisted by :func:`HoistFromSwitchSuccessors`
// * PHINodes are allowed in any block
// * if there are 2 exits it is allowed that the one exitBB have CFG path to other exitBB
//   and blocks between exitBB0 and exitBB1 may have a path from BB0 which does not contain exitBB0/1
// * the region may have also other unreachable exits
// * exitBB blocks do not need to be dominated by BB0
//
// .. code-block::cpp
//    switch(c0) {
//    case 0: {
//      if (c1) {
//         return;	
//      }	
//    	break;   
//    }
//    case 1: {
//      if (c2) {
//         return;	
//      }	
//    	break;   
//    }
//    default:
//       unreachable();
//    }
//    bbExit1:
//
//    // to:
//    if ((c0==0 & c1) || (c0 == 1 && c2))
//        return;
//    bbExit1:
//
// call map:
// .. code-block::
//     HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit
//         HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_matchPattern
//         lowerPhisToSelectInRegion
//         
// 
bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::SwitchInst &SI, bool &exprChanged);
}
