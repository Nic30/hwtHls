# Machine code for function linearSequenceOfBlocksWithSameTail: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.BB0:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  dead %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %3:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, %2:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %14:anyregcls(s1) = G_AND killed %2:anyregcls, killed %3:anyregcls
  %4:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, %14:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %15:anyregcls(s1) = G_AND killed %14:anyregcls, killed %4:anyregcls
  dead %5:anyregcls = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, killed %15:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_RET

# End machine code for function linearSequenceOfBlocksWithSameTail.

