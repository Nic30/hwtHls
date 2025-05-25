# Machine code for function triangle: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 0, killed %1:anyregcls, 0, 8, killed %2:anyregcls :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_RET

# End machine code for function triangle.

