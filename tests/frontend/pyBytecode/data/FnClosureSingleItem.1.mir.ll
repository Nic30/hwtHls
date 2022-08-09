# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL22i0_22:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.i)
  GENFPGA_CSTORE %2:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  G_BR %bb.1

# End machine code for function mainThread.

