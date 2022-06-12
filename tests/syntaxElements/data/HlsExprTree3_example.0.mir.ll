# Machine code for function t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %11:anyregcls(s32) = GENFPGA_CLOAD %0:anyregcls(s1), 1 :: (volatile load (s32) from %ir.a)
  %12:anyregcls(s32) = GENFPGA_CLOAD %1:anyregcls(s1), 1 :: (volatile load (s32) from %ir.b)
  %13:anyregcls(s32) = GENFPGA_CLOAD %2:anyregcls(s1), 1 :: (volatile load (s32) from %ir.c)
  %14:anyregcls(s32) = GENFPGA_CLOAD %3:anyregcls(s1), 1 :: (volatile load (s32) from %ir.d)
  %15:anyregcls(s32) = G_ADD %12:anyregcls, %11:anyregcls
  %16:anyregcls(s32) = G_ADD %15:anyregcls, %13:anyregcls
  %17:anyregcls(s32) = G_MUL %16:anyregcls, %14:anyregcls
  GENFPGA_CSTORE %17:anyregcls(s32), %4:anyregcls(s1), 1 :: (volatile store (s32) into %ir.f1)
  %18:anyregcls(s32) = GENFPGA_CLOAD %8:anyregcls(s1), 1 :: (volatile load (s32) from %ir.x)
  %19:anyregcls(s32) = GENFPGA_CLOAD %9:anyregcls(s1), 1 :: (volatile load (s32) from %ir.y)
  %20:anyregcls(s32) = G_ADD %19:anyregcls, %18:anyregcls
  %21:anyregcls(s32) = GENFPGA_CLOAD %10:anyregcls(s1), 1 :: (volatile load (s32) from %ir.z)
  %22:anyregcls(s32) = G_MUL %20:anyregcls, %21:anyregcls
  GENFPGA_CSTORE %22:anyregcls(s32), %5:anyregcls(s1), 1 :: (volatile store (s32) into %ir.f2)
  %23:anyregcls(s32) = GENFPGA_CLOAD %7:anyregcls(s1), 1 :: (volatile load (s32) from %ir.w)
  %24:anyregcls(s32) = G_MUL %23:anyregcls, %20:anyregcls
  GENFPGA_CSTORE %24:anyregcls(s32), %6:anyregcls(s1), 1 :: (volatile store (s32) into %ir.f3)
  G_BR %bb.1

# End machine code for function t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example.

