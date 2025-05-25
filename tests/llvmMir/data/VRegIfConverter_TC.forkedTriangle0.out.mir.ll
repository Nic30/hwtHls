# Machine code for function forkedTriangle0: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  successors: %bb.2(0x66666666), %bb.1(0x1999999a); %bb.2(80.00%), %bb.1(20.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 0, %1:anyregcls, 0, 8, %2:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %4:anyregcls(s1) = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, %2:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %9:anyregcls(s1) = G_CONSTANT i1 true
  %8:anyregcls(s1) = G_XOR killed %4:anyregcls, killed %9:anyregcls
  %10:anyregcls(s1) = G_AND killed %2:anyregcls, killed %8:anyregcls
  G_BRCOND killed %10:anyregcls(s1), %bb.1
  G_BR %bb.2

bb.1.BBLoop:
; predecessors: %bb.1, %bb.0
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  HWTFPGA_CSTORE i8 1, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.1

bb.2.FBB:
; predecessors: %bb.0

  HWTFPGA_RET

# End machine code for function forkedTriangle0.

