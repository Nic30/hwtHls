# Machine code for function forkedTriangleWhichIsLoopInLoop0: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.BBEntry:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.BBLoopHead:
; predecessors: %bb.0, %bb.2
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  HWTFPGA_CSTORE i8 0, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)

bb.2.EBB:
; predecessors: %bb.1, %bb.2
  successors: %bb.2(0x7c000000), %bb.1(0x04000000); %bb.2(96.88%), %bb.1(3.12%)

  %3:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 1, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  %5:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, %3:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 2, %1:anyregcls, 0, 8, %3:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %15:anyregcls(s1) = G_CONSTANT i1 true
  %14:anyregcls(s1) = G_XOR killed %5:anyregcls, killed %15:anyregcls
  %16:anyregcls(s1) = G_AND killed %3:anyregcls, killed %14:anyregcls
  %18:anyregcls(s1) = G_CONSTANT i1 true
  %17:anyregcls(s1) = G_XOR killed %16:anyregcls, killed %18:anyregcls
  HWTFPGA_CSTORE i8 3, %1:anyregcls, 0, 8, killed %17:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_CSTORE i8 4, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  %9:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  G_BRCOND killed %9:anyregcls, %bb.2
  G_BR %bb.1

# End machine code for function forkedTriangleWhichIsLoopInLoop0.

