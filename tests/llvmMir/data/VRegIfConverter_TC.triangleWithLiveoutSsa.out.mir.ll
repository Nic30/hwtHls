# Machine code for function triangleWithLiveoutSsa: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %5:anyregcls = G_CONSTANT i8 2
  %6:anyregcls = G_CONSTANT i8 3
  %2:anyregcls = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 0, %1:anyregcls, 0, 8, %2:anyregcls :: (volatile store (s8) into %ir.o, addrspace 2)
  %4:anyregcls = G_SELECT killed %2:anyregcls, %6:anyregcls, %5:anyregcls
  HWTFPGA_CSTORE killed %4:anyregcls, killed %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_RET

# End machine code for function triangleWithLiveoutSsa.

