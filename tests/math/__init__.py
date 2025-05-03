"""
How FP intrinsic functions/opcodes are defined:
-----------------------------------------------
Frontend:
* tests.math.hFloatTmp.hFloatTmpOps contains the definition of python function
  this function construct an expression HOperatorDefLlvm associated with this function e.g. fadd construct expr with OP_FADD
* The operator holds method to translate itself into llvm, usually one of
  * native llvm operator like fneg
  * llvm::LibFunc call e.g. LibFunc::LibFunc_atan2
  * generic CallInst

LLVM IR:
* Until hwtHls::HFloatTmpLoweringPass the functions are using double type,
  the code which uses double is an island which have hwtHls.fp.castToHFloatTmp / hwtHls.fp.castFromHFloatTmp
  on its boundaries. Input and output type must match.
* after hwtHls::HFloatTmpLoweringPass are in specialized format which replaces each FP function/operand with intrinsics
  defined in hfloattmp.h, these functions have all HFloatTmpConfig members as arguments.

LLVM MIR:
* LLVM IR specialized instructions are lowered by HwtFpgaCallLowering which translates specialized intrinsics
  to a machine instructions with HWTFPGA_* opcode 

HlsNetlist:
* HlsNetlistAnalysisPassMirToNetlist translates MahineInstr back to original HOperatorDefLlvm definition and construct
  HlsNetNodeOperator from it with HFloatTmpConfig as its specialization.
* HOperatorDefLlvm is then used to lookup ComponentGenerator associated with the HOperatorDefLlvm in
  HlsPlatform._componentGenerators.
* ComponentGenerator holds all scheduling info and it also resolves physical realization of function.


Python math libraries with definitions of math functions:
* [mpmath](https://github.com/mpmath/mpmath)


"""