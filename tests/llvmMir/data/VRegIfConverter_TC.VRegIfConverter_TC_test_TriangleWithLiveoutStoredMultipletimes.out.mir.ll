# Machine code for function VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.test_TriangleWithLiveoutStoredMultipletimes:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls(s1) = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s16) from %ir.iC0, addrspace 1)
  %3:anyregcls(s64) = HWTFPGA_MUX i64 0
  dead %6:anyregcls(s64) = HWTFPGA_MUX i64 1
  %6:anyregcls(s64) = HWTFPGA_MUX i64 3
  %3:anyregcls(s64) = HWTFPGA_MUX killed %3:anyregcls(s64), killed %2:anyregcls(s1), killed %6:anyregcls(s64)
  HWTFPGA_CSTORE killed %3:anyregcls(s64), killed %1:anyregcls, 0, 64, 1 :: (volatile store (s64) into %ir.o, align 4, addrspace 2)
  HWTFPGA_RET

# End machine code for function VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes.

