# Machine code for function simpleWithTooManyBranches: IsSSA, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  successors: %bb.1(0x40000000), %bb.4(0x40000000); %bb.1(50.00%), %bb.4(50.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  HWTFPGA_CSTORE i8 0, %1:anyregcls, 0, 8, %2:anyregcls :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BRCOND killed %2:anyregcls, %bb.4

bb.1.FBB:
; predecessors: %bb.0
  successors: %bb.2(0x40000000), %bb.3(0x40000000); %bb.2(50.00%), %bb.3(50.00%)

  %3:anyregcls(s1) = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  G_BRCOND killed %3:anyregcls(s1), %bb.2
  G_BR %bb.3

bb.2.FTBB:
; predecessors: %bb.2, %bb.1
  successors: %bb.2(0x80000000); %bb.2(100.00%)

  HWTFPGA_CSTORE i8 3, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.2

bb.3.FFBB:
; predecessors: %bb.3, %bb.1
  successors: %bb.3(0x80000000); %bb.3(100.00%)

  HWTFPGA_CSTORE i8 2, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.3

bb.4.L0:
; predecessors: %bb.4, %bb.0
  successors: %bb.4(0x80000000); %bb.4(100.00%)

  HWTFPGA_CSTORE i8 1, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.4

# End machine code for function simpleWithTooManyBranches.

