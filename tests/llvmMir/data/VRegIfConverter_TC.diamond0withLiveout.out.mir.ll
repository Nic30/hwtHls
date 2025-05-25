# Machine code for function diamond0withLiveout: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EBB:
  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %6:anyregcls = G_CONSTANT i8 2
  %7:anyregcls = G_CONSTANT i8 3
  %2:anyregcls(s1) = HWTFPGA_CLOAD killed %0:anyregcls, 0, 1, 1 :: (volatile load (s1) from %ir.iC0, addrspace 1)
  %12:anyregcls(s1) = G_CONSTANT i1 true
  %11:anyregcls(s1) = G_XOR %2:anyregcls, killed %12:anyregcls
  HWTFPGA_CSTORE i8 11, %1:anyregcls, 0, 8, killed %11:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %10:anyregcls = COPY killed %7:anyregcls
  HWTFPGA_CSTORE i8 10, %1:anyregcls, 0, 8, %2:anyregcls(s1) :: (volatile store (s8) into %ir.o, addrspace 2)
  %13:anyregcls = COPY killed %6:anyregcls
  %10:anyregcls = HWTFPGA_MUX killed %13:anyregcls, killed %2:anyregcls(s1), killed %10:anyregcls
  %5:anyregcls = COPY killed %10:anyregcls
  HWTFPGA_CSTORE killed %5:anyregcls, killed %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  HWTFPGA_RET

# End machine code for function diamond0withLiveout.

