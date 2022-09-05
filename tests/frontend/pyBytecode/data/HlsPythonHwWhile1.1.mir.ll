# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL20i0_20:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  %7:anyregcls(s8) = GENFPGA_MUX i8 0

bb.2.blockL20i0_L22i0_22:
; predecessors: %bb.1, %bb.2
  successors: %bb.1(0x04000000), %bb.2(0x7c000000); %bb.1(3.12%), %bb.2(96.88%)

  %2:anyregcls(s8) = GENFPGA_MUX %7:anyregcls(s8)
  GENFPGA_CSTORE %2:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  %4:anyregcls(s8) = G_ADD %7:anyregcls, i8 1
  %5:anyregcls(s1) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s1) from %ir.i_rst, addrspace 1)
  %7:anyregcls(s8) = GENFPGA_MUX %4:anyregcls(s8)
  %8:anyregcls(s1) = GENFPGA_NOT %5:anyregcls(s1)
  G_BRCOND %8:anyregcls(s1), %bb.2
  G_BR %bb.1

# End machine code for function mainThread.

