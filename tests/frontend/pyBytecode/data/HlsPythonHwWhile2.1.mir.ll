# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %13:anyregcls(s8) = GENFPGA_MUX i8 0

bb.1.blockL20i0_20:
; predecessors: %bb.0, %bb.3
  successors: %bb.2(0x40000000), %bb.4(0x40000000); %bb.2(50.00%), %bb.4(50.00%)

  %1:anyregcls(s8) = GENFPGA_MUX %13:anyregcls(s8)
  %3:anyregcls(s1) = G_ICMP intpred(uge), %13:anyregcls(s8), i8 5
  G_BRCOND %3:anyregcls(s1), %bb.4

bb.2.blockL20i0_28:
; predecessors: %bb.1
  successors: %bb.3(0x80000000); %bb.3(100.00%)

  GENFPGA_CSTORE %1:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)

bb.3.blockL20i0_56:
; predecessors: %bb.4, %bb.2
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %8:anyregcls(s8) = G_ADD %13:anyregcls, i8 1
  %13:anyregcls(s8) = GENFPGA_MUX %8:anyregcls(s8)
  G_BR %bb.1

bb.4.blockL20i0_44:
; predecessors: %bb.1
  successors: %bb.5(0x04000000), %bb.3(0x7c000000); %bb.5(3.12%), %bb.3(96.88%)

  %5:anyregcls(s1) = G_ICMP intpred(ne), %13:anyregcls(s8), i8 10
  G_BRCOND %5:anyregcls(s1), %bb.3

bb.5.blockL84i0_84:
; predecessors: %bb.5, %bb.4
  successors: %bb.5(0x80000000); %bb.5(100.00%)

  GENFPGA_CSTORE i8 0, %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  G_BR %bb.5

# End machine code for function mainThread.

