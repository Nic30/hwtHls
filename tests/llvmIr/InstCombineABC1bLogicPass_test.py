#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function, FunctionPassManager, InstCombineABC1bLogicPass
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.stripInstructionsUnrelatedToCrash import llvmIrStripInstrucionsUnrelatedToCrash
# from tests.stripInstructionsUnrelatedToCrash import llvmIrStripInstrucionsUnrelatedToCrash


def _addBitwidthReductionPass(FPM: FunctionPassManager):
    FPM.addPass(InstCombineABC1bLogicPass())


class InstCombineABC1bLogicPass_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle) -> Function:
        return llvm._runCustomFunctionPass(_addBitwidthReductionPass)

    def test_constInConcat0(self):
        llvmIr = """\
define void @main(ptr addrspace(1) %a1, ptr addrspace(2) %a2, ptr addrspace(3) %a3, ptr addrspace(4) %a4, ptr addrspace(5) %a5, ptr addrspace(6) %a6, ptr addrspace(7) %a7, ptr addrspace(8) %a8, ptr addrspace(9) %a9, ptr addrspace(10) %a10, ptr addrspace(11) %a11, ptr addrspace(12) %a12, ptr addrspace(13) %a13, ptr addrspace(14) %a14, ptr addrspace(15) %a15, ptr addrspace(16) %a16, ptr addrspace(17) %a17, ptr addrspace(18) %a18, ptr addrspace(19) %a19) {
entry:
  %v1 = load i1, ptr addrspace(1) %a1, align 1
  %v2 = load i1, ptr addrspace(2) %a2, align 1
  %v3 = load i1, ptr addrspace(3) %a3, align 1
  %v4 = load i1, ptr addrspace(4) %a4, align 1
  %v5 = load i1, ptr addrspace(5) %a5, align 1
  %v6 = load i1, ptr addrspace(6) %a6, align 1
  %v7 = load i1, ptr addrspace(7) %a7, align 1
  %v8 = load i1, ptr addrspace(8) %a8, align 1
  %v9 = load i1, ptr addrspace(9) %a9, align 1
  %v10 = load i1, ptr addrspace(10) %a10, align 1
  %v11 = load i1, ptr addrspace(11) %a11, align 1
  %v12 = and i1 false, false
  store volatile i1 %v12, ptr addrspace(12) %a12, align 1
  %v13 = icmp eq i3 0, 0
  %v14 = or i1 false, %v13
  %v15 = icmp eq i3 0, 0
  %v16 = and i1 %v1, false
  %v17 = and i1 false, false
  store volatile i1 %v17, ptr addrspace(13) %a13, align 1
  %v18 = and i1 false, false
  store volatile i1 %v18, ptr addrspace(14) %a14, align 1
  %v19 = and i1 %v15, %v11
  %v20 = and i1 %v13, %v19
  %v21 = icmp eq i3 0, 0
  %v22 = and i1 %v21, %v20
  %v23 = and i1 %v3, %v6
  %v24 = and i1 %v3, %v13
  %v25 = xor i1 %v24, true
  %v26 = and i1 %v13, %v10
  %v27 = and i1 %v26, %v1
  %v28 = or i1 %v8, false
  %v29 = and i1 %v9, %v28
  %v30 = or i1 %v27, %v29
  %v31 = and i1 %v30, %v25
  %v32 = or i1 %v23, %v31
  %v33 = and i1 false, false
  %v34 = xor i1 false, true
  %v35 = and i1 %v32, %v34
  %v36 = and i1 false, false
  %v37 = or i1 false, false
  %v38 = xor i1 false, true
  %v39 = and i1 %v2, %v5
  %v40 = and i1 %v39, %v38
  %v41 = and i1 %v40, %v4
  %v42 = or i1 false, %v4
  %v43 = and i1 %v14, %v42
  %v44 = and i1 %v43, %v30
  %v45 = and i1 %v41, %v44
  %v46 = and i1 %v45, %v7
  %v47 = select i1 %v22, i1 %v46, i1 %v35
  store volatile i1 %v47, ptr addrspace(15) %a15, align 1
  store volatile i1 %v14, ptr addrspace(16) %a16, align 1
  %v48 = and i1 false, false
  store volatile i1 %v48, ptr addrspace(17) %a17, align 1
  %v49 = and i1 false, false
  store volatile i1 %v49, ptr addrspace(18) %a18, align 1
  store volatile i1 %v37, ptr addrspace(19) %a19, align 1
  %v50 = and i1 false, false
  %v51 = select i1 %v28, i6 0, i6 0
  %v52 = select i1 %v42, i6 0, i6 0
  %v53 = select i1 %v27, i6 0, i6 0
  %v54 = select i1 %v50, i8 0, i8 0
  %v55 = or i1 false, false
  %v56 = and i1 false, false
  %v57 = and i1 false, false
  %v58 = select i1 %v57, i6 0, i6 0
  %v59 = select i1 %v36, i6 0, i6 0
  %v60 = select i1 %v33, i6 0, i6 0
  %v61 = select i1 %v56, i6 0, i6 0
  %v62 = select i1 %v55, i6 0, i6 0
  ret void
}
        """
        #llvm = llvmIrStripInstrucionsUnrelatedToCrash(llvmIr, lambda llvm: self._runTestOpt(llvm))
        #print(str(llvm.main))
        self._test_ll(llvmIr)


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(InstCombineABC1bLogicPass_TC)
    # suite = unittest.TestSuite([BitwidthReductionPass_TC('test_0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
