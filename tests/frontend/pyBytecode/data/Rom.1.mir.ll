# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL32i0_32:
; predecessors: %bb.0, %bb.6
  successors: %bb.5(0x20000000), %bb.2(0x60000000); %bb.5(25.00%), %bb.2(75.00%)

  %2:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i)
  %4:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 -2
  G_BRCOND %4:anyregcls(s1), %bb.5

bb.2.blockL32i0_32:
; predecessors: %bb.1
  successors: %bb.6(0x2aaaaaab), %bb.3(0x55555555); %bb.6(33.33%), %bb.3(66.67%)

  %6:anyregcls(s1) = G_ICMP intpred(eq), %2:anyregcls(s2), i2 0
  %16:anyregcls(s32) = GENFPGA_MUX i32 1
  G_BRCOND %6:anyregcls(s1), %bb.6

bb.3.blockL32i0_32:
; predecessors: %bb.2
  successors: %bb.6(0x80000000); %bb.6(100.00%)

  %8:anyregcls(s1) = G_ICMP intpred(ne), %2:anyregcls(s2), i2 1
  %16:anyregcls(s32) = GENFPGA_MUX i32 2
  %16:anyregcls(s32) = GENFPGA_MUX i32 8, %8:anyregcls(s1)
  G_BR %bb.6

bb.5.blockL32i0_32_getSwEnd.fold.split3:
; predecessors: %bb.1
  successors: %bb.6(0x80000000); %bb.6(100.00%)

  %16:anyregcls(s32) = GENFPGA_MUX i32 4

bb.6.blockL32i0_32_getSwEnd:
; predecessors: %bb.2, %bb.5, %bb.3
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %9:anyregcls(s32) = GENFPGA_MUX %16:anyregcls(s32)
  GENFPGA_CSTORE %9:anyregcls(s32), %1:anyregcls, 0, 1 :: (volatile store (s32) into %ir.o, addrspace 1)
  G_BR %bb.1

# End machine code for function mainThread.

