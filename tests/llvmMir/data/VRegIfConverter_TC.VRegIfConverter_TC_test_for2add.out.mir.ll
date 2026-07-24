# Machine code for function VRegIfConverter_TC_test_for2add: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.bb0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %1:anyregcls = HWTFPGA_ARG_GET 0
  %3:anyregcls(s3) = HWTFPGA_MUX i3 1
  %4:anyregcls(s3) = HWTFPGA_IMPLICIT_DEF 3
  %5:anyregcls(s1) = HWTFPGA_IMPLICIT_DEF 1
  %9:anyregcls(s1) = HWTFPGA_MUX i1 true

bb.1.bb3:
; predecessors: %bb.1, %bb.0
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %10:anyregcls(s3) = HWTFPGA_MUX i3 0
  %11:anyregcls(s1) = HWTFPGA_MUX i1 false
  %4:anyregcls(s3) = HWTFPGA_MUX killed %10:anyregcls(s3), %9:anyregcls(s1), %4:anyregcls(s3)
  %5:anyregcls(s1) = HWTFPGA_MUX killed %11:anyregcls(s1), %9:anyregcls(s1), %5:anyregcls(s1)
  %4:anyregcls(s3) = HWTFPGA_ADD %4:anyregcls(s3), %3:anyregcls(s3)
  %6:anyregcls(s1) = HWTFPGA_NOT %5:anyregcls(s1)
  %5:anyregcls(s1) = HWTFPGA_MUX i1 true
  %8:anyregcls(s1) = G_CONSTANT i1 true
  %7:anyregcls(s1) = G_XOR killed %6:anyregcls, killed %8:anyregcls
  HWTFPGA_CSTORE %4:anyregcls(s3), %1:anyregcls, 0, 3, %7:anyregcls(s1) :: (volatile store (s3) into %ir.data_out, addrspace 2)
  %9:anyregcls(s1) = HWTFPGA_MUX killed %7:anyregcls(s1)
  G_BR %bb.1

# End machine code for function VRegIfConverter_TC_test_for2add.

