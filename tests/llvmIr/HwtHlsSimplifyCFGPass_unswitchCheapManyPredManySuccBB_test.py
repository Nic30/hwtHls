#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC


class HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB_test_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm, *args, **kwargs)

    def test_unswitchCheap0(self):
        llvmIr = """\
define void @HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB_test_TC.test_unswitchCheap0(ptr addrspace(1) %i, ptr addrspace(2) %o)  {
bb0:
  %st = alloca i3, align 1
  br label %bb.header

bb.header:         ; preds = %bb0, %bb.latch
  %c = load volatile i3, ptr addrspace(1) %i, align 4
  %br.en.2 = load volatile i1, ptr addrspace(1) %i, align 4
  %br.en.3 = load volatile i1, ptr addrspace(1) %i, align 4
  %br.en.5 = load volatile i1, ptr addrspace(1) %i, align 4
  %d.0 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.1 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.5 = load volatile i8, ptr addrspace(1) %i, align 4
  %d.6 = load volatile i8, ptr addrspace(1) %i, align 4
  switch i3 %c, label %bb.caseDef [
    i3 0, label %bb.case0
    i3 1, label %bb.case1
    i3 2, label %bb.case2
    i3 3, label %bb.case3
  ]

bb.caseDef:                   ; preds = %bb.header
  unreachable

bb.case0:                                              ; preds = %bb.header
  br i1 %br.en.5, label %bb.toUnswitch, label %bb.latch

bb.case1:                                           ; preds = %bb.header
  store volatile i8 0, ptr addrspace(2) %o, align 4
  br label %bb.toUnswitch

bb.case2:                                           ; preds = %bb.header
  store volatile i8 %d.0, ptr addrspace(2) %o, align 4
  br label %bb.toUnswitch

bb.toUnswitch:                                          ; preds = %bb.case0, %bb.case1, %bb.case2
  %d.7 = phi i8 [ %d.1, %bb.case0 ], [ %d.0, %bb.case1 ], [ %d.0, %bb.case2 ]
  %br.en.0 = phi i1 [ false, %bb.case0 ], [ true, %bb.case1 ], [ false, %bb.case2 ]
  br i1 %br.en.0, label %bb.latch, label %bb.case3 ; %br.en.0 known from cfg, this block is cheap => copy and prune successor
  ; however, the problem is that the %br.en.0 has also other uses

bb.case3:                                ; preds = %bb.header, %bb.toUnswitch
  %d.2 = phi i8 [ %d.0, %bb.header ], [ %d.1, %bb.toUnswitch ]
  %br.en.1 = phi i1 [ %br.en.2, %bb.header ], [ %br.en.0, %bb.toUnswitch ]
  %d.8 = select i1 %br.en.1, i8 %d.5, i8 %d.6
  store volatile i8 %d.8, ptr addrspace(2) %o, align 4
  br label %bb.latch

bb.latch:          ; preds = %bb.toUnswitch, %bb.case0, %bb.case3
  %d.3 = phi i8 [ %d.7, %bb.toUnswitch ], [ %d.1, %bb.case0 ], [ %d.2, %bb.case3 ]
  %br.en.4 = phi i1 [ %br.en.0, %bb.toUnswitch ], [ %br.en.3, %bb.case0 ], [ %br.en.1, %bb.case3 ]
  store volatile i8 %d.3, ptr addrspace(2) %o, align 4
  store volatile i1 %br.en.4, ptr addrspace(2) %o, align 4
  br label %bb.header
}
        """
        self._test_ll(llvmIr,
                     passKwArgs=dict(
                         # dumpDotBeforeToFile="tmp/simplifyCfg0.dot",
                         # dumpDotAfterToFile="tmp/simplifyCfg1.dot",
                         # BonusInstThreshold=30,
                         )
                      )


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB_test_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC('test_0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
