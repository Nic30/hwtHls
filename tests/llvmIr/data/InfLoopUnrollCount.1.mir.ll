# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %7:anyregcls(s8) = GENFPGA_MUX i8 0

bb.1.blockL20i0_20:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %1:anyregcls(s8) = GENFPGA_MUX %7:anyregcls(s8)
  GENFPGA_CSTORE %1:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  %3:anyregcls(s8) = G_ADD %7:anyregcls, i8 1
  GENFPGA_CSTORE %3:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  %4:anyregcls(s8) = G_ADD %3:anyregcls, i8 1
  GENFPGA_CSTORE %4:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  %5:anyregcls(s8) = G_ADD %4:anyregcls, i8 1
  %7:anyregcls(s8) = GENFPGA_MUX %5:anyregcls(s8)
  G_BR %bb.1

# End machine code for function mainThread.
