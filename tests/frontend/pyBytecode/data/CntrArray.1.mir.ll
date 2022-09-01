# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %42:anyregcls(s16) = GENFPGA_MUX i16 0
  %43:anyregcls(s16) = GENFPGA_MUX i16 0
  %44:anyregcls(s16) = GENFPGA_MUX i16 0
  %45:anyregcls(s16) = GENFPGA_MUX i16 0

bb.1.blockL54i0_54:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %7:anyregcls(s2) = GENFPGA_CLOAD %2:anyregcls, 0, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 3)
  %9:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 -2
  %11:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 0
  %13:anyregcls(s1) = G_ICMP intpred(ne), %7:anyregcls(s2), i2 1
  %14:anyregcls(s16) = GENFPGA_MUX %44:anyregcls(s16), %9:anyregcls(s1), %42:anyregcls(s16), %11:anyregcls(s1), %45:anyregcls(s16), %13:anyregcls(s1), %43:anyregcls(s16)
  %15:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
  GENFPGA_CSTORE %14:anyregcls(s16), %1:anyregcls, 0, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
  %16:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 0
  %17:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 -2
  %46:anyregcls(s1) = GENFPGA_EXTRACT %15:anyregcls(s2), 1, 1
  %20:anyregcls(s1) = GENFPGA_NOT %46:anyregcls(s1)
  %47:anyregcls(s1) = G_AND %16:anyregcls, %20:anyregcls
  %22:anyregcls(s16) = GENFPGA_MUX %42:anyregcls(s16), %47:anyregcls(s1), %43:anyregcls(s16), %20:anyregcls(s1), %44:anyregcls(s16), %17:anyregcls(s1), %45:anyregcls(s16)
  %24:anyregcls(s16) = G_ADD %22:anyregcls, i16 1
  %25:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 1
  %42:anyregcls(s16) = GENFPGA_MUX %24:anyregcls(s16), %16:anyregcls(s1), %42:anyregcls(s16)
  %43:anyregcls(s16) = GENFPGA_MUX %43:anyregcls(s16), %16:anyregcls(s1), %24:anyregcls(s16), %25:anyregcls(s1), %43:anyregcls(s16)
  %44:anyregcls(s16) = GENFPGA_MUX %44:anyregcls(s16), %16:anyregcls(s1), %44:anyregcls(s16), %25:anyregcls(s1), %24:anyregcls(s16), %17:anyregcls(s1), %44:anyregcls(s16)
  %45:anyregcls(s16) = GENFPGA_MUX %45:anyregcls(s16), %16:anyregcls(s1), %45:anyregcls(s16), %25:anyregcls(s1), %45:anyregcls(s16), %17:anyregcls(s1), %24:anyregcls(s16)
  G_BR %bb.1

# End machine code for function mainThread.

