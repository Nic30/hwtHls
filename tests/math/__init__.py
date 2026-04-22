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


Math libraries with definitions of elementary math functions:
* [mpmath](https://github.com/mpmath/mpmath)
* [gmp](https://github.com/Halliburton-Landmark/gmp/tree/master/mpn/generic)
* [libtom/tomsfastmath](https://github.com/libtom/tomsfastmath) [libtom/libtommath](https://github.com/libtom/libtommath)
* [tomverbeure/math](https://github.com/tomverbeure/math) math library for SpinalHDL
* [FloppyFloat](https://github.com/not-chciken/FloppyFloat) soft math library for ISA simulators
* [simple-soft-float](https://salsa.debian.org/Kazan-team/simple-soft-float)
* [sfpy](https://github.com/billzorn/sfpy) softfloat and softposit in Python

Math focused compilers
* https://github.com/diku-dk/futhark
"""
