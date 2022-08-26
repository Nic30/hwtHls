# Machine code for function t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=4, align=4, at location [SP+2]

bb.0.t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s16) from %ir.a, addrspace 1)
  %3:anyregcls(s32) = GENFPGA_MERGE_VALUES %2:anyregcls(s16), i16 16, 16, 16
  GENFPGA_CSTORE %3:anyregcls(s32), %1:anyregcls, 0, 1 :: (volatile store (s32) into %ir.b, addrspace 2)
  G_BR %bb.1

# End machine code for function t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice.

