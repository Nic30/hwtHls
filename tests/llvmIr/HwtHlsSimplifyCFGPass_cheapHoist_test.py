#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwtHls.llvm.llvmIr import LlvmCompilationBundle, Function
from tests.llvmIr.baseLlvmIrTC import BaseLlvmIrTC
from tests.llvmIr.HwtHlsSimplifyCFGPass_test import HwtHlsSimplifyCFGPass_TC
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS


class HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC(BaseLlvmIrTC):
    __FILE__ = __file__

    def _runTestOpt(self, llvm:LlvmCompilationBundle, *args, **kwargs) -> Function:
        return HwtHlsSimplifyCFGPass_TC._runTestOpt(self, llvm)

    def test_preserveBrCond_0(self):
        # based on:
        # m = Axi4SCrc32()
        # m.CRC_MAX_BYTES_PROCESSED_IN_PARALLEL = 2
        # m.DATA_WIDTH = 4 * 8
        llvmIr = """\
define void @test_preserveBrCond_0(ptr addrspace(1) %crcOut, ptr addrspace(2) %i) {
bb0:
  br label %bb.L0.head

bb.L0.head:                                  ; preds = %bb0, %bb.L0.latch
  br label %bb.L1.head

bb.L1.head:                           ; preds = %bb.L1.latch, %bb.L0.head
  %crcAcc.0 = phi i32 [ -1, %bb.L0.head ], [ %19, %bb.L1.latch ]
  %i_read1.r0 = load volatile i37, ptr addrspace(2) %i, align 8
  %0 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.0(i37 %i_read1.r0, i7 0) #2
  %1 = call i16 @hwtHls.bitRangeGet.i37.i7.i16.16(i37 %i_read1.r0, i7 16) #2
  %2 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %i_read1.r0, i7 35) #2
  %3 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %i_read1.r0, i7 34) #2
  %i_read1.r0.eof = call i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %i_read1.r0, i7 36) #2
  %i_read1.r0.mask = call i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %i_read1.r0, i7 32) #2
  %4 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %i_read1.r0, i7 32) #2
  %5 = call i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %i_read1.r0, i7 33) #2
  %8 = xor i1 %5, true
  %9 = and i1 %i_read1.r0.eof, %8
  %10 = xor i1 %9, true
  %11 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %10) #2
  %12 = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i16(i32 0, i32 %crcAcc.0, i16 %0, i2 %11) #2
  br i1 %9, label %bb.L0.latch, label %bb.L1.1

bb.L1.1:                         ; preds = %bb.L1.head
  %13 = xor i1 %3, true
  %14 = and i1 %i_read1.r0.eof, %13
  br i1 %14, label %bb.L0.latch, label %bb.L1.2

bb.L1.2:                         ; preds = %bb.L1.1
  %15 = xor i1 %2, true
  %16 = and i1 %i_read1.r0.eof, %15
  ;%16 = load volatile i1, ptr addrspace(2) %i, align 8
  %17 = xor i1 %16, true
  %18 = call i2 @hwtHls.bitConcat.i1.i1(i1 true, i1 %17) #2
  %19 = call i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i16(i32 0, i32 %12, i16 %1, i2 %18) #2
  br i1 %16, label %bb.L0.latch, label %bb.L1.latch

bb.L1.latch:                         ; preds = %bb.L1.2
  br i1 %i_read1.r0.eof, label %bb.L0.latch, label %bb.L1.head

bb.L0.latch:                                  ; preds = %bb.L1.latch, %bb.L1.2, %bb.L1.1, %bb.L1.head
  ; HwtHlsSimplifyCFGPass_phiToLogicalExpr
  %.lcssa = phi i32 [ %12, %bb.L1.head ], [ %12, %bb.L1.1 ], [ %19, %bb.L1.2 ], [ %19, %bb.L1.latch ]
  %20 = call i32 @hwtHls.pyObjectPlaceholder.1.CrcFinalizeHardblock.i32(i32 1, i32 %.lcssa) #2
  store volatile i32 %20, ptr addrspace(1) %crcOut, align 4
  br label %bb.L0.head
}


; Function Attrs: nofree nounwind willreturn
declare !hwtHls.mergableFunction.statePlusMaskedData !6 i32 @hwtHls.pyObjectPlaceholder.0.crc.CRC_32.i16(i32, i32, i16, i2) #10

; Function Attrs: nofree nounwind speculatable willreturn
declare i32 @hwtHls.pyObjectPlaceholder.1.CrcFinalizeHardblock.i32(i32, i32) #11

declare i1 @hwtHls.bitRangeGet.i37.i7.i1.32(i37 %0, i7 %1) #1
declare i1 @hwtHls.bitRangeGet.i37.i7.i1.33(i37 %0, i7 %1) #1
declare i1 @hwtHls.bitRangeGet.i37.i7.i1.34(i37 %0, i7 %1) #1
declare i1 @hwtHls.bitRangeGet.i37.i7.i1.35(i37 %0, i7 %1) #1
declare i1 @hwtHls.bitRangeGet.i37.i7.i1.36(i37 %0, i7 %1) #1
declare i16 @hwtHls.bitRangeGet.i37.i7.i16.0(i37 %0, i7 %1) #1
declare i16 @hwtHls.bitRangeGet.i37.i7.i16.16(i37 %0, i7 %1) #1
declare i2 @hwtHls.bitConcat.i1.i1(i1 %0, i1 %1) #1
declare i4 @hwtHls.bitRangeGet.i37.i7.i4.32(i37 %0, i7 %1) #1
attributes #1 = { nofree nounwind speculatable willreturn }
attributes #2 = { memory(none) }
attributes #10 = { nofree nounwind willreturn }
attributes #11 = { nofree nounwind speculatable willreturn }

!6 = distinct !{!6, i32 1}
!7 = !{}
        """
        self._test_ll(llvmIr, use_generateAndAppendHwtHlsFunctionDeclarations=False,
                      llvmCliArgs=[
                          # ("hwthls-simplifycfg-SwitchReduceRange", 0, "", "false"),
                          # ("hwthls-simplifycfg-HoistHoistableAssumes", 0, "", "false"),
                          # ("hwthls-simplifycfg-NormalizeLookupTableIndex", 0, "", "false"),
                          # ("hwthls-simplifycfg-RewriteMaskPatternsFromCFGToData", 0, "", "false"),
                          # ("hwthls-simplifycfg-StoreHoist", 0, "", "false"),
                          # ("hwthls-simplifycfg-AggresiveStoreSink", 0, "", "false"),
                          # ("hwthls-simplifycfg-MergePredecessorsStore", 0, "", "false"),
                          # ("hwthls-simplifycfg-PhiToLogicalExpr", 0, "", "false"),
                          # ("hwthls-simplifycfg-UnswitchComplementarySequentialBlocks", 0, "", "false"),
                          # ("hwthls-simplifycfg-SpeculatePredecessor", 0, "", "false"),
                          # ("hwthls-simplifycfg-StreamWriteMerge", 0, "", "false"),
                          # ("hwthls-simplifycfg-StreamReadMerge", 0, "", "false"),
                          # ("hwthls-simplifycfg-SwitchToSelectOrRomLoad", 0, "", "false"),
                          # ("hwthls-simplifycfg-NormalizeBrCond", 0, "", "false"),
                          # ("hwthls-simplifycfg-ConstantFoldTerminator", 0, "", "false"),
                          # ("hwthls-simplifycfg-EliminateDuplicatePHINodes", 0, "", "false"),
                          # ("hwthls-simplifycfg-EemoveUndefIntroducingPredecessor", 0, "", "false"),
                          # ("hwthls-simplifycfg-MergeBlockIntoPredecessor", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunEarlyCSEPass", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunRomExtractPass", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunHwtHlsInstCombinePass", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunTrivialSimplifyCFGPass", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunSimplifyCFGPass", 0, "", "false"),
                          # ("hwthls-simplifycfg-RunBitcountMergePass", 0, "", "false"),
                        # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                        # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                        LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                        # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                        # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                      ],

                      )


if __name__ == "__main__":
    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_TC)
    # suite = unittest.TestSuite([HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_TC('test_0')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
