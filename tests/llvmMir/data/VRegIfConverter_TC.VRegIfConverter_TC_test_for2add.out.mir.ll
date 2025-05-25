# Machine code for function VRegIfConverter_TC_test_for2add: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.bb0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %1:anyregcls = HWTFPGA_ARG_GET 0
  %3:anyregcls = HWTFPGA_MUX i3 1

bb.1.bb2:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %4:anyregcls = HWTFPGA_MUX i3 0
  %5:anyregcls = HWTFPGA_MUX i1 false

bb.2.bb3:
; predecessors: %bb.1, %bb.2
  successors: %bb.2(0x7c000000), %bb.1(0x04000000); %bb.2(96.88%), %bb.1(3.12%)

  %4:anyregcls = HWTFPGA_ADD %4:anyregcls, %3:anyregcls
  %6:anyregcls(s1) = HWTFPGA_NOT %5:anyregcls
  %5:anyregcls = HWTFPGA_MUX i1 true
  %8:anyregcls(s1) = G_CONSTANT i1 true
  %7:anyregcls(s1) = G_XOR killed %6:anyregcls, killed %8:anyregcls
  HWTFPGA_CSTORE %4:anyregcls, %1:anyregcls, 0, 2, %7:anyregcls(s1) :: (volatile store (s2) into %ir.data_out, addrspace 2)
  G_BRCOND killed %7:anyregcls(s1), %bb.1
  G_BR %bb.2

# End machine code for function VRegIfConverter_TC_test_for2add.

