# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL10i0_10:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %10:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.a, addrspace 1)
  %11:anyregcls(s8) = GENFPGA_CLOAD %1:anyregcls, 0, 1 :: (volatile load (s8) from %ir.b, addrspace 2)
  %12:anyregcls(s1) = G_ICMP intpred(ule), %10:anyregcls(s8), %11:anyregcls
  GENFPGA_CSTORE %12:anyregcls(s1), %2:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res, addrspace 3)
  GENFPGA_CSTORE i1 true, %9:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_same, addrspace 10)
  GENFPGA_CSTORE %12:anyregcls(s1), %6:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_same, addrspace 7)
  GENFPGA_CSTORE %12:anyregcls(s1), %8:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_same_1, addrspace 9)
  GENFPGA_CSTORE %12:anyregcls(s1), %3:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_0vs1, addrspace 4)
  GENFPGA_CSTORE %12:anyregcls(s1), %4:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_0vsAll, addrspace 5)
  GENFPGA_CSTORE %12:anyregcls(s1), %7:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_sameInMiddle, addrspace 8)
  GENFPGA_CSTORE %12:anyregcls(s1), %5:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_differentInMiddle, addrspace 6)
  G_BR %bb.1

# End machine code for function mainThread.

