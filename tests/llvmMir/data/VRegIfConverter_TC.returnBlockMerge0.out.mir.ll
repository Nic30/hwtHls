# Machine code for function returnBlockMerge0: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.bb.0:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %4:anyregcls = G_CONSTANT i4 1
  %5:anyregcls = G_CONSTANT i4 2
  dead %2:anyregcls = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %3:anyregcls = HWTFPGA_MERGE_VALUES killed %4:anyregcls, killed %5:anyregcls, 4, 4
  HWTFPGA_CSTORE killed %3:anyregcls, killed %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_RET

# End machine code for function returnBlockMerge0.

