# Machine code for function SwitchInLoop1: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_Axi4SParse2IfAndSequel:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %8:anyregcls = G_CONSTANT i1 true
  %9:anyregcls = G_CONSTANT i1 false

bb.1.bb0:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 16, 1 :: (volatile load (s16) from %ir.i, addrspace 1)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls, i16 2
  %12:anyregcls = COPY %8:anyregcls
  %6:anyregcls(s1) = G_ICMP intpred(ne), killed %2:anyregcls, i16 1
  %21:anyregcls = COPY %9:anyregcls
  %12:anyregcls = HWTFPGA_MUX %12:anyregcls, %4:anyregcls(s1), killed %21:anyregcls
  %23:anyregcls(s1) = G_CONSTANT i1 true
  %22:anyregcls(s1) = G_XOR killed %4:anyregcls, killed %23:anyregcls
  %24:anyregcls(s1) = G_AND killed %22:anyregcls, killed %6:anyregcls
  %7:anyregcls = COPY killed %12:anyregcls
  %26:anyregcls(s1) = G_CONSTANT i1 true
  %25:anyregcls(s1) = G_XOR killed %24:anyregcls, killed %26:anyregcls
  HWTFPGA_CSTORE killed %7:anyregcls, %1:anyregcls, 0, 1, killed %25:anyregcls(s1) :: (volatile store (s1) into %ir.o, align 2, addrspace 2)
  G_BR %bb.1

# End machine code for function SwitchInLoop1.

