# Machine code for function diamond1: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls(s1) = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %8:anyregcls(s1) = G_CONSTANT i1 true
  %7:anyregcls(s1) = G_XOR %2:anyregcls, killed %8:anyregcls
  HWTFPGA_CSTORE i8 11, %1:anyregcls, 0, 8, killed %7:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_CSTORE i8 10, killed %1:anyregcls, 0, 8, killed %2:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_RET

# End machine code for function diamond1.

