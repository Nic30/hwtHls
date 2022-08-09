# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL10i0_10:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  GENFPGA_CSTORE i8 10, %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o)
  G_BR %bb.1

# End machine code for function mainThread.

