# Machine code for function t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=4, align=4, at location [SP+2]

bb.0.t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = GENFPGA_CLOAD %0:anyregcls(s1), 1 :: (volatile load (s16) from %ir.a)
  %3:anyregcls(s32) = GENFPGA_MERGE_VALUES i11 0, i1 true, i4 0, %2:anyregcls(s16), 11, 1, 4, 16
  GENFPGA_CSTORE %3:anyregcls(s32), %1:anyregcls(s1), 1 :: (volatile store (s32) into %ir.b)
  G_BR %bb.1

# End machine code for function t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat.

