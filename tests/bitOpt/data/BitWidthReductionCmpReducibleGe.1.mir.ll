# Machine code for function mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected
Frame Objects:
  fi#0: size=2, align=2, at location [SP+2]
  fi#1: size=2, align=2, at location [SP+2]
  fi#2: size=2, align=2, at location [SP+2]
  fi#3: size=2, align=2, at location [SP+2]
  fi#4: size=2, align=2, at location [SP+2]
  fi#5: size=1, align=1, at location [SP+2]
  fi#6: size=1, align=1, at location [SP+2]
  fi#7: size=2, align=2, at location [SP+2]
  fi#8: size=1, align=1, at location [SP+2]
  fi#9: size=1, align=1, at location [SP+2]
  fi#10: size=2, align=2, at location [SP+2]
  fi#11: size=2, align=2, at location [SP+2]

bb.0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.blockL10i0_10:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %10:anyregcls(s8) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s8) from %ir.a, addrspace 1)
  %11:anyregcls(s8) = GENFPGA_CLOAD %1:anyregcls, 0, 1 :: (volatile load (s8) from %ir.b, addrspace 2)
  %12:anyregcls(s1) = G_ICMP intpred(uge), %10:anyregcls(s8), %11:anyregcls
  GENFPGA_CSTORE %12:anyregcls(s1), %2:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res, addrspace 3)
  GENFPGA_CSTORE i1 true, %9:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_same, addrspace 10)
  %14:anyregcls(s16) = GENFPGA_MERGE_VALUES %10:anyregcls(s8), i8 0, 8, 8
  %17:anyregcls(s16) = GENFPGA_MERGE_VALUES %11:anyregcls(s8), i8 0, 8, 8
  %19:anyregcls(s1) = G_ICMP intpred(uge), %14:anyregcls(s16), %17:anyregcls
  GENFPGA_CSTORE %19:anyregcls(s1), %6:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_same, addrspace 7)
  %20:anyregcls(s16) = GENFPGA_MERGE_VALUES %10:anyregcls(s8), i8 1, 8, 8
  %23:anyregcls(s16) = GENFPGA_MERGE_VALUES %11:anyregcls(s8), i8 1, 8, 8
  %25:anyregcls(s1) = G_ICMP intpred(uge), %20:anyregcls(s16), %23:anyregcls
  GENFPGA_CSTORE %25:anyregcls(s1), %8:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_same_1, addrspace 9)
  %26:anyregcls(s1) = G_ICMP intpred(uge), %14:anyregcls(s16), %23:anyregcls
  GENFPGA_CSTORE %26:anyregcls(s1), %3:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_0vs1, addrspace 4)
  %27:anyregcls(s16) = GENFPGA_MERGE_VALUES %11:anyregcls(s8), i8 -1, 8, 8
  %30:anyregcls(s1) = G_ICMP intpred(uge), %14:anyregcls(s16), %27:anyregcls
  GENFPGA_CSTORE %30:anyregcls(s1), %4:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_0vsAll, addrspace 5)
  %31:anyregcls(s4) = GENFPGA_EXTRACT %10:anyregcls(s8), 0, 4
  %34:anyregcls(s4) = GENFPGA_EXTRACT %10:anyregcls(s8), 4, 4
  %37:anyregcls(s16) = GENFPGA_MERGE_VALUES %31:anyregcls(s4), i8 0, %34:anyregcls(s4), 4, 8, 4
  %39:anyregcls(s4) = GENFPGA_EXTRACT %11:anyregcls(s8), 0, 4
  %41:anyregcls(s4) = GENFPGA_EXTRACT %11:anyregcls(s8), 4, 4
  %43:anyregcls(s16) = GENFPGA_MERGE_VALUES %39:anyregcls(s4), i8 0, %41:anyregcls(s4), 4, 8, 4
  %45:anyregcls(s1) = G_ICMP intpred(uge), %37:anyregcls(s16), %43:anyregcls
  GENFPGA_CSTORE %45:anyregcls(s1), %7:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_sameInMiddle, addrspace 8)
  %46:anyregcls(s16) = GENFPGA_MERGE_VALUES %39:anyregcls(s4), i8 -1, %41:anyregcls(s4), 4, 8, 4
  %48:anyregcls(s1) = G_ICMP intpred(uge), %37:anyregcls(s16), %46:anyregcls
  GENFPGA_CSTORE %48:anyregcls(s1), %5:anyregcls, 0, 1 :: (volatile store (s1) into %ir.res_prefix_differentInMiddle, addrspace 6)
  G_BR %bb.1

# End machine code for function mainThread.

