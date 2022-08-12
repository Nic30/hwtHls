# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %42:anyregcls(s512) = GENFPGA_MUX i512 0
  %43:anyregcls(s512) = GENFPGA_MUX i512 0
  %44:anyregcls(s512) = GENFPGA_MUX i512 0
  %45:anyregcls(s512) = GENFPGA_MUX i512 0

bb.1.blockL54i0_54:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %7:anyregcls(s2) = GENFPGA_CLOAD %2:anyregcls, 0, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 2)
  %9:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 -2
  %11:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 0
  %13:anyregcls(s1) = G_ICMP intpred(ne), %7:anyregcls(s2), i2 1
  %14:anyregcls(s512) = GENFPGA_MUX %44:anyregcls(s512), %9:anyregcls(s1), %42:anyregcls(s512), %11:anyregcls(s1), %45:anyregcls(s512), %13:anyregcls(s1), %43:anyregcls(s512)
  GENFPGA_CSTORE %14:anyregcls(s512), %1:anyregcls, 0, 1 :: (volatile store (s512) into %ir.o, align 4, addrspace 1)
  %15:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i)
  %16:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 0
  %17:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 -2
  %18:anyregcls(s512) = GENFPGA_MUX %42:anyregcls(s512), %16:anyregcls(s1), %43:anyregcls(s512)
  %20:anyregcls(s1) = G_ICMP intpred(sgt), %15:anyregcls(s2), i2 -1
  %22:anyregcls(s512) = GENFPGA_MUX %18:anyregcls(s512), %20:anyregcls(s1), %44:anyregcls(s512), %17:anyregcls(s1), %45:anyregcls(s512)
  %24:anyregcls(s512) = G_ADD %22:anyregcls, i512 1
  %25:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 1
  %42:anyregcls(s512) = GENFPGA_MUX %24:anyregcls(s512), %16:anyregcls(s1), %42:anyregcls(s512)
  %43:anyregcls(s512) = GENFPGA_MUX %43:anyregcls(s512), %16:anyregcls(s1), %24:anyregcls(s512), %25:anyregcls(s1), %43:anyregcls(s512)
  %44:anyregcls(s512) = GENFPGA_MUX %44:anyregcls(s512), %16:anyregcls(s1), %44:anyregcls(s512), %25:anyregcls(s1), %24:anyregcls(s512), %17:anyregcls(s1), %44:anyregcls(s512)
  %45:anyregcls(s512) = GENFPGA_MUX %45:anyregcls(s512), %16:anyregcls(s1), %45:anyregcls(s512), %25:anyregcls(s1), %45:anyregcls(s512), %17:anyregcls(s1), %24:anyregcls(s512)
  G_BR %bb.1

# End machine code for function mainThread.

