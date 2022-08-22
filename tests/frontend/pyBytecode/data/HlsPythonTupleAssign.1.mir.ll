# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=1, align=1, at location [SP+2]
  fi#1: size=1, align=1, at location [SP+2]

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %11:anyregcls(s1) = GENFPGA_MUX i1 false
  %12:anyregcls(s1) = GENFPGA_MUX i1 true

bb.1.blockL30i0_30:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s1) = GENFPGA_MUX %11:anyregcls(s1)
  %4:anyregcls(s8) = GENFPGA_MERGE_VALUES %11:anyregcls(s1), i7 0, 1, 7
  GENFPGA_CSTORE %4:anyregcls(s8), %0:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o0)
  %7:anyregcls(s8) = GENFPGA_MERGE_VALUES %12:anyregcls(s1), i7 0, 1, 7
  GENFPGA_CSTORE %7:anyregcls(s8), %1:anyregcls, 0, 1 :: (volatile store (s8) into %ir.o1, addrspace 1)
  %11:anyregcls(s1) = GENFPGA_MUX %12:anyregcls(s1)
  %12:anyregcls(s1) = GENFPGA_MUX %2:anyregcls(s1)
  G_BR %bb.1

# End machine code for function mainThread.

