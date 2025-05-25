# Machine code for function LoopTail0: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.BB0:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  dead %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.BBL0:
; predecessors: %bb.0, %bb.1
  successors: %bb.2(0x07e00000), %bb.1(0x78200000); %bb.2(6.15%), %bb.1(93.85%)

  %2:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %3:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, %2:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %8:anyregcls(s1) = G_AND killed %2:anyregcls, killed %3:anyregcls
  G_BRCOND killed %8:anyregcls(s1), %bb.1

bb.2.BBExit:
; predecessors: %bb.1

  HWTFPGA_RET

# End machine code for function LoopTail0.

