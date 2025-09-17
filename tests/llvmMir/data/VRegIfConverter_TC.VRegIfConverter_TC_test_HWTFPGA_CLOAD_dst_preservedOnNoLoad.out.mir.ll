# Machine code for function VRegIfConverter_TC_test_HWTFPGA_CLOAD_dst_preservedOnNoLoad: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.VRegIfConverter_TC_test_HWTFPGA_CLOAD_dst_preservedOnNoLoad:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %7:anyregcls = HWTFPGA_MUX i1 false
  %8:anyregcls = HWTFPGA_MUX i8 0

bb.1.WhileSendSequence1.mainLoop:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls = HWTFPGA_MUX %8:anyregcls
  %3:anyregcls = HWTFPGA_ICMP intpred(ne), %2:anyregcls, i8 0
  %4:anyregcls(s1) = HWTFPGA_OR %7:anyregcls, killed %3:anyregcls
  HWTFPGA_CSTORE %2:anyregcls, %1:anyregcls, 0, 8, %4:anyregcls(s1) :: (volatile store (s8) into %ir.dataOut, addrspace 2)
  %13:anyregcls = HWTFPGA_ADD %2:anyregcls, i8 -1
  %5:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), killed %2:anyregcls, i8 1
  %14:anyregcls = HWTFPGA_MUX i1 true
  %8:anyregcls = HWTFPGA_MUX killed %13:anyregcls, %4:anyregcls(s1), %8:anyregcls
  %7:anyregcls = HWTFPGA_MUX killed %14:anyregcls, %4:anyregcls(s1), %7:anyregcls
  %15:anyregcls(s1) = G_AND killed %4:anyregcls, killed %5:anyregcls
  %17:anyregcls(s1) = G_CONSTANT i1 true
  %16:anyregcls(s1) = G_XOR %15:anyregcls, killed %17:anyregcls
  %18:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, killed %16:anyregcls(s1) :: (volatile load (s8) from %ir.dataIn, addrspace 1)
  %19:anyregcls = HWTFPGA_MUX i1 false
  %8:anyregcls = HWTFPGA_MUX %8:anyregcls, %15:anyregcls(s1), killed %18:anyregcls
  %7:anyregcls = HWTFPGA_MUX %7:anyregcls, killed %15:anyregcls(s1), killed %19:anyregcls
  G_BR %bb.1

# End machine code for function VRegIfConverter_TC_test_HWTFPGA_CLOAD_dst_preservedOnNoLoad.

