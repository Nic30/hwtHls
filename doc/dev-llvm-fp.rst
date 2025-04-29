Floating/fixed point in LLVM
============================

* llvm fp functions are realized using llvm operators, intrisic functions and library call
  * The optimization of FP expressions is the part of the llvm::InstCombinePass
    if the function is realized as library call the llvm::InstCombinePass calls llvm::LibCallSimplifier
* hwtHls uses HFloatTmp islands to represent float/fixed point arithmetic regions
  * the region begins with hwtHls.fp.castToHFloatTmp and ends with hwtHls.fp.castFromHFloatTmp
    both instructions hold the info about type (HFloatTmpConfig) and the type must be same
    for whole region
  * the HFloatTmp region is then specialized to a concrete type in hwtHls::HFloatTmpLoweringPass

