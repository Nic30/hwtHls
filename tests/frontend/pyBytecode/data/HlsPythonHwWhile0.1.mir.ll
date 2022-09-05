# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %8:anyregcls(s8) = GENFPGA_MUX i8 0

bb.1.blockL20i0_20:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %4:anyregcls(s8) = G_ADD %8:anyregcls, i8 1
  GENFPGA_CSTORE %4:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  %5:anyregcls(s1) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s1) from %ir.i_rst, addrspace 1)
  %8:anyregcls(s8) = GENFPGA_MUX i8 0, %5:anyregcls(s1), %4:anyregcls(s8)
  G_BR %bb.1

# End machine code for function mainThread.

