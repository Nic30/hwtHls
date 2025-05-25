# Machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.bb0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb2:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %42:anyregcls(s2) = HWTFPGA_MUX i2 0
  %43:anyregcls(s3) = HWTFPGA_MUX i3 0
  %44:anyregcls(s16) = HWTFPGA_IMPLICIT_DEF 16

bb.2.bb3:
; predecessors: %bb.1, %bb.2
  successors: %bb.1(0x04000000), %bb.2(0x7c000000); %bb.1(3.12%), %bb.2(96.88%)

  %5:anyregcls(s2) = HWTFPGA_EXTRACT %43:anyregcls(s3), 3, 0, 2
  %7:anyregcls(s10) = HWTFPGA_CLOAD %0:anyregcls, 0, 10, 1 :: (volatile load (s10) from %ir.rx, addrspace 1)
  %8:anyregcls(s8) = HWTFPGA_EXTRACT %7:anyregcls(s10), 10, 0, 8
  %10:anyregcls(s1) = HWTFPGA_EXTRACT %7:anyregcls(s10), 10, 9, 1
  %12:anyregcls(s5) = HWTFPGA_MERGE_VALUES i3 0, %42:anyregcls(s2), 3, 2
  %16:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12:anyregcls(s5), i5 -16
  %45:anyregcls(s27) = HWTFPGA_MERGE_VALUES %44:anyregcls(s16), %8:anyregcls(s8), %5:anyregcls(s2), i1 true, 16, 8, 2, 1
  %46:anyregcls(s16) = HWTFPGA_IMPLICIT_DEF 16
  %18:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12:anyregcls(s5), i5 8
  %65:anyregcls(s27) = HWTFPGA_MERGE_VALUES %8:anyregcls(s8), undef %28:anyregcls(s16), i3 1, 8, 16, 3
  %49:anyregcls(s16) = HWTFPGA_MERGE_VALUES %8:anyregcls(s8), undef %24:anyregcls(s8), 8, 8
  %19:anyregcls(s8) = HWTFPGA_EXTRACT %44:anyregcls(s16), 16, 0, 8
  %20:anyregcls(s1) = HWTFPGA_EXTRACT %43:anyregcls(s3), 3, 0, 1
  %21:anyregcls(s1) = HWTFPGA_EXTRACT %43:anyregcls(s3), 3, 2, 1
  %60:anyregcls(s27) = HWTFPGA_MERGE_VALUES %19:anyregcls(s8), %8:anyregcls(s8), undef %24:anyregcls(s8), %20:anyregcls(s1), i1 true, %21:anyregcls(s1), 8, 8, 8, 1, 1, 1
  %25:anyregcls(s16) = HWTFPGA_MERGE_VALUES %19:anyregcls(s8), %8:anyregcls(s8), 8, 8
  %61:anyregcls(s3) = HWTFPGA_MERGE_VALUES %20:anyregcls(s1), i1 true, %21:anyregcls(s1), 1, 1, 1
  %65:anyregcls(s27) = HWTFPGA_MUX %60:anyregcls(s27), %18:anyregcls(s1), %65:anyregcls(s27)
  %66:anyregcls(s16) = HWTFPGA_MUX %25:anyregcls(s16), %18:anyregcls(s1), %49:anyregcls(s16)
  %49:anyregcls(s16) = HWTFPGA_MUX %25:anyregcls(s16), %18:anyregcls(s1), %49:anyregcls(s16)
  %45:anyregcls(s27) = HWTFPGA_MUX %45:anyregcls(s27), %16:anyregcls(s1), %65:anyregcls(s27)
  %46:anyregcls(s16) = HWTFPGA_MUX %46:anyregcls(s16), %16:anyregcls(s1), %66:anyregcls(s16)
  %67:anyregcls(s1) = HWTFPGA_NOT %16:anyregcls(s1)
  %69:anyregcls(s1) = HWTFPGA_NOT %10:anyregcls(s1)
  %71:anyregcls(s1) = HWTFPGA_AND %67:anyregcls(s1), %69:anyregcls(s1)
  %33:anyregcls(s28) = HWTFPGA_MERGE_VALUES %45:anyregcls(s27), %10:anyregcls(s1), 27, 1
  %72:anyregcls(s1) = HWTFPGA_NOT %71:anyregcls(s1)
  HWTFPGA_CSTORE %33:anyregcls(s28), %1:anyregcls, 0, 28, %72:anyregcls(s1) :: (volatile store (s28) into %ir.txBody, addrspace 2)
  %78:anyregcls = HWTFPGA_AND %18:anyregcls(s1), %71:anyregcls(s1)
  %49:anyregcls(s16) = HWTFPGA_MUX %49:anyregcls(s16), %71:anyregcls(s1), %46:anyregcls(s16)
  %42:anyregcls(s2) = HWTFPGA_MUX i2 -2, %78:anyregcls, i2 1, %71:anyregcls(s1), i2 0
  %43:anyregcls(s3) = HWTFPGA_MUX %61:anyregcls(s3), %78:anyregcls, i3 1, %71:anyregcls(s1), i3 0
  %44:anyregcls(s16) = HWTFPGA_MUX %49:anyregcls(s16)
  HWTFPGA_BRCOND %10:anyregcls(s1), %bb.1
  HWTFPGA_BR %bb.2

# End machine code for function HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0.

