# Machine code for function noOptSingleBlock: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.bb.0:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %2:anyregcls = G_CONSTANT i4 1
  %3:anyregcls = G_CONSTANT i4 2
  %1:anyregcls = HWTFPGA_MERGE_VALUES killed %2:anyregcls, killed %3:anyregcls, 4, 4
  HWTFPGA_CSTORE killed %1:anyregcls, killed %0:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
  HWTFPGA_RET

# End machine code for function noOptSingleBlock.

