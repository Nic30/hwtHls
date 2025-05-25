# Machine code for function forkedTriangleInLoop: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.BBEntry:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.BBLoopHead:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 0, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  %4:anyregcls(s1) = HWTFPGA_CLOAD %0:anyregcls, 0, 1, %2:anyregcls(s1) :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 1, %1:anyregcls, 0, 8, %2:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %13:anyregcls(s1) = G_CONSTANT i1 true
  %12:anyregcls(s1) = G_XOR killed %4:anyregcls, killed %13:anyregcls
  %14:anyregcls(s1) = G_AND killed %2:anyregcls, killed %12:anyregcls
  %16:anyregcls(s1) = G_CONSTANT i1 true
  %15:anyregcls(s1) = G_XOR killed %14:anyregcls, killed %16:anyregcls
  HWTFPGA_CSTORE i8 2, %1:anyregcls, 0, 8, killed %15:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_CSTORE i8 3, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.1

# End machine code for function forkedTriangleInLoop.

