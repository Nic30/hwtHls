# Machine code for function VRegIfConverter_TC_test_TriangleFalseWithLoopLatch: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.VRegIfConverter_TC_test_TriangleFalseWithLoopLatch:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb1:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %2:anyregcls = HWTFPGA_IMPLICIT_DEF 16

bb.2.head:
; predecessors: %bb.1, %bb.2
  successors: %bb.2(0x66666666), %bb.1(0x1999999a); %bb.2(80.00%), %bb.1(20.00%)

  %3:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.rx, addrspace 1)
  %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2:anyregcls, i16 99
  %5:anyregcls = HWTFPGA_MUX %2:anyregcls
  %8:anyregcls = HWTFPGA_MUX killed %5:anyregcls, %4:anyregcls(s1), %2:anyregcls
  %2:anyregcls = HWTFPGA_MUX %2:anyregcls, %3:anyregcls(s1), killed %8:anyregcls
  %10:anyregcls(s1) = G_CONSTANT i1 true
  %9:anyregcls(s1) = G_XOR killed %3:anyregcls, killed %10:anyregcls
  %12:anyregcls(s1) = G_CONSTANT i1 true
  %11:anyregcls(s1) = G_XOR killed %4:anyregcls, killed %12:anyregcls
  %13:anyregcls(s1) = G_AND killed %9:anyregcls, killed %11:anyregcls
  HWTFPGA_CSTORE %2:anyregcls, %1:anyregcls, 0, 16, %13:anyregcls(s1) :: (volatile store (s16) into %ir.txBody, addrspace 2)
  G_BRCOND killed %13:anyregcls(s1), %bb.1
  G_BR %bb.2

# End machine code for function VRegIfConverter_TC_test_TriangleFalseWithLoopLatch.

