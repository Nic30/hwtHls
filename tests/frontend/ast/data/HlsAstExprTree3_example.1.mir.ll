# Machine code for function t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example:
  successors: %bb.1(0x80000000); %bb.1(100.00%)


bb.1.t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_whC:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %11:anyregcls(s32) = GENFPGA_CLOAD %0:anyregcls, 0, 1 :: (volatile load (s32) from %ir.a)
  %12:anyregcls(s32) = GENFPGA_CLOAD %1:anyregcls, 0, 1 :: (volatile load (s32) from %ir.b, addrspace 1)
  %13:anyregcls(s32) = GENFPGA_CLOAD %2:anyregcls, 0, 1 :: (volatile load (s32) from %ir.c, addrspace 2)
  %14:anyregcls(s32) = GENFPGA_CLOAD %3:anyregcls, 0, 1 :: (volatile load (s32) from %ir.d, addrspace 3)
  %15:anyregcls(s32) = G_ADD %12:anyregcls, %11:anyregcls
  %16:anyregcls(s32) = G_ADD %15:anyregcls, %13:anyregcls
  %17:anyregcls(s32) = G_MUL %16:anyregcls, %14:anyregcls
  GENFPGA_CSTORE %17:anyregcls(s32), %4:anyregcls, 0, 1 :: (volatile store (s32) into %ir.f1, addrspace 4)
  %18:anyregcls(s32) = GENFPGA_CLOAD %8:anyregcls, 0, 1 :: (volatile load (s32) from %ir.x, addrspace 8)
  %19:anyregcls(s32) = GENFPGA_CLOAD %9:anyregcls, 0, 1 :: (volatile load (s32) from %ir.y, addrspace 9)
  %20:anyregcls(s32) = G_ADD %19:anyregcls, %18:anyregcls
  %21:anyregcls(s32) = GENFPGA_CLOAD %10:anyregcls, 0, 1 :: (volatile load (s32) from %ir.z, addrspace 10)
  %22:anyregcls(s32) = G_MUL %20:anyregcls, %21:anyregcls
  GENFPGA_CSTORE %22:anyregcls(s32), %5:anyregcls, 0, 1 :: (volatile store (s32) into %ir.f2, addrspace 5)
  %23:anyregcls(s32) = GENFPGA_CLOAD %7:anyregcls, 0, 1 :: (volatile load (s32) from %ir.w, addrspace 7)
  %24:anyregcls(s32) = G_MUL %23:anyregcls, %20:anyregcls
  GENFPGA_CSTORE %24:anyregcls(s32), %6:anyregcls, 0, 1 :: (volatile store (s32) into %ir.f3, addrspace 6)
  G_BR %bb.1

# End machine code for function t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example.

