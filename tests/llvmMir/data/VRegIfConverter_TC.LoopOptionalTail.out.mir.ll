# Machine code for function LoopOptionalTail: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.HlsPythonHwWhile3.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.bb1:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
  %4:anyregcls(s1) = G_ICMP intpred(eq), killed %2:anyregcls, i8 1
  %12:anyregcls(s1) = G_CONSTANT i1 true
  %11:anyregcls(s1) = G_XOR killed %4:anyregcls, killed %12:anyregcls
  %5:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, %11:anyregcls(s1) :: (volatile load (s8) from %ir.i, addrspace 1)
  HWTFPGA_CSTORE %5:anyregcls, %1:anyregcls, 0, 8, %11:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %7:anyregcls(s1) = G_ICMP intpred(eq), killed %5:anyregcls, i8 2
  %13:anyregcls(s1) = G_AND killed %11:anyregcls, killed %7:anyregcls
  %15:anyregcls(s1) = G_CONSTANT i1 true
  %14:anyregcls(s1) = G_XOR killed %13:anyregcls, killed %15:anyregcls
  HWTFPGA_CSTORE i8 99, %1:anyregcls, 0, 8, killed %14:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.1

# End machine code for function LoopOptionalTail.

