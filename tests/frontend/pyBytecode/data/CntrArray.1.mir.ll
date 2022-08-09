# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %31:anyregcls(s512) = GENFPGA_MUX i512 0
  %32:anyregcls(s512) = GENFPGA_MUX i512 0
  %33:anyregcls(s512) = GENFPGA_MUX i512 0
  %34:anyregcls(s512) = GENFPGA_MUX i512 0

bb.1.blockL54i0_54:
; predecessors: %bb.0, %bb.6, %bb.7, %bb.8
  successors: %bb.5(0x20000000), %bb.2(0x60000000); %bb.5(25.00%), %bb.2(75.00%)

  %6:anyregcls(s512) = GENFPGA_MUX %34:anyregcls(s512)
  %5:anyregcls(s512) = GENFPGA_MUX %33:anyregcls(s512)
  %4:anyregcls(s512) = GENFPGA_MUX %32:anyregcls(s512)
  %3:anyregcls(s512) = GENFPGA_MUX %31:anyregcls(s512)
  %7:anyregcls(s2) = GENFPGA_CLOAD %2:anyregcls, 0, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 2)
  %9:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 -2
  G_BRCOND %9:anyregcls(s1), %bb.5

bb.2.blockL54i0_54:
; predecessors: %bb.1
  successors: %bb.6(0x2aaaaaab), %bb.3(0x55555555); %bb.6(33.33%), %bb.3(66.67%)

  %11:anyregcls(s1) = G_ICMP intpred(eq), %7:anyregcls(s2), i2 0
  %35:anyregcls(s512) = GENFPGA_MUX %3:anyregcls(s512)
  G_BRCOND %11:anyregcls(s1), %bb.6

bb.3.blockL54i0_54:
; predecessors: %bb.2
  successors: %bb.6(0x80000000); %bb.6(100.00%)

  %13:anyregcls(s1) = G_ICMP intpred(ne), %7:anyregcls(s2), i2 1
  %35:anyregcls(s512) = GENFPGA_MUX %4:anyregcls(s512)
  %35:anyregcls(s512) = GENFPGA_MUX %6:anyregcls(s512), %13:anyregcls(s1)
  G_BR %bb.6

bb.5.blockL54i0_54_getSwEnd.fold.split7:
; predecessors: %bb.1
  successors: %bb.6(0x80000000); %bb.6(100.00%)

  %35:anyregcls(s512) = GENFPGA_MUX %5:anyregcls(s512)

bb.6.blockL54i0_54_getSwEnd:
; predecessors: %bb.2, %bb.5, %bb.3
  successors: %bb.1(0x30000000), %bb.7(0x50000000); %bb.1(37.50%), %bb.7(62.50%)

  %14:anyregcls(s512) = GENFPGA_MUX %35:anyregcls(s512)
  GENFPGA_CSTORE %14:anyregcls(s512), %1:anyregcls, 0, 1 :: (volatile store (s512) into %ir.o, align 4, addrspace 1)
  %15:anyregcls(s2) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s2) from %ir.i)
  %16:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 0
  %17:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 -2
  %18:anyregcls(s512) = GENFPGA_MUX %31:anyregcls(s512), %16:anyregcls(s1), %32:anyregcls(s512)
  %20:anyregcls(s1) = G_ICMP intpred(sgt), %15:anyregcls(s2), i2 -1
  %21:anyregcls(s512) = GENFPGA_MUX %33:anyregcls(s512), %17:anyregcls(s1), %34:anyregcls(s512)
  %22:anyregcls(s512) = GENFPGA_MUX %18:anyregcls(s512), %20:anyregcls(s1), %21:anyregcls(s512)
  %24:anyregcls(s512) = G_ADD %22:anyregcls, i512 1
  %31:anyregcls(s512) = GENFPGA_MUX %24:anyregcls(s512)
  %32:anyregcls(s512) = GENFPGA_MUX %4:anyregcls(s512)
  %33:anyregcls(s512) = GENFPGA_MUX %5:anyregcls(s512)
  %34:anyregcls(s512) = GENFPGA_MUX %6:anyregcls(s512)
  G_BRCOND %16:anyregcls(s1), %bb.1

bb.7.blockL54i0_54_getSwEnd_getSwEnd5:
; predecessors: %bb.6
  successors: %bb.1(0x40000000), %bb.8(0x40000000); %bb.1(50.00%), %bb.8(50.00%)

  %25:anyregcls(s1) = G_ICMP intpred(eq), %15:anyregcls(s2), i2 1
  %31:anyregcls(s512) = GENFPGA_MUX %3:anyregcls(s512)
  %32:anyregcls(s512) = GENFPGA_MUX %24:anyregcls(s512)
  %33:anyregcls(s512) = GENFPGA_MUX %5:anyregcls(s512)
  %34:anyregcls(s512) = GENFPGA_MUX %6:anyregcls(s512)
  G_BRCOND %25:anyregcls(s1), %bb.1

bb.8.blockL54i0_54_getSwEnd_getSwEnd6:
; predecessors: %bb.7
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %26:anyregcls(s512) = GENFPGA_MUX %34:anyregcls(s512), %17:anyregcls(s1), %24:anyregcls(s512)
  %27:anyregcls(s512) = GENFPGA_MUX %24:anyregcls(s512), %17:anyregcls(s1), %33:anyregcls(s512)
  %31:anyregcls(s512) = GENFPGA_MUX %3:anyregcls(s512)
  %32:anyregcls(s512) = GENFPGA_MUX %4:anyregcls(s512)
  %33:anyregcls(s512) = GENFPGA_MUX %27:anyregcls(s512)
  %34:anyregcls(s512) = GENFPGA_MUX %26:anyregcls(s512)
  G_BR %bb.1

# End machine code for function mainThread.

