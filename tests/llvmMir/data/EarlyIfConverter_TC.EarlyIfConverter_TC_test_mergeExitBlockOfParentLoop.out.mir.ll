# Machine code for function EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.blockL44i0_44:
; predecessors: %bb.0, %bb.5, %bb.6
  successors: %bb.2(0x40000000), %bb.6(0x40000000); %bb.2(50.00%), %bb.6(50.00%)

  dead %2:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %3:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %4:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %5:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %6:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %7:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %8:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %9:anyregcls(s16) = HWTFPGA_EXTRACT %8:anyregcls(s19), 19, 0, 16
  %12:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %9:anyregcls(s16), i16 2048
  %56:anyregcls(s1) = HWTFPGA_NOT %12:anyregcls(s1)
  HWTFPGA_BRCOND %56:anyregcls(s1), %bb.6

bb.2.blockL44i0_244:
; predecessors: %bb.1
  successors: %bb.3(0x80000000); %bb.3(100.00%)

  dead %16:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %17:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %18:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %19:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %20:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %21:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %22:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %23:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %24:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  dead %25:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %47:anyregcls(s8) = HWTFPGA_MUX i8 0
  %48:anyregcls(s1) = HWTFPGA_MUX i1 false

bb.3.blockL44i0_L376i0_376:
; predecessors: %bb.2, %bb.4
  successors: %bb.5(0x04000000), %bb.4(0x7c000000); %bb.5(3.12%), %bb.4(96.88%)

  %27:anyregcls(s1) = HWTFPGA_MUX %48:anyregcls(s1)
  %26:anyregcls(s8) = HWTFPGA_MUX %47:anyregcls(s8)
  %28:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %29:anyregcls(s1) = HWTFPGA_EXTRACT %28:anyregcls(s19), 19, 18, 1
  %30:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %26:anyregcls(s8), i1 false, %27:anyregcls(s1), i1 false, 8, 8, 1, 1, 1
  HWTFPGA_CSTORE %30:anyregcls(s19), %0:anyregcls, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
  %49:anyregcls(s19) = HWTFPGA_MUX %28:anyregcls(s19)
  HWTFPGA_BRCOND %29:anyregcls(s1), %bb.5

bb.4.blockL44i0_L376i0_376.1:
; predecessors: %bb.3
  successors: %bb.5(0x04000000), %bb.3(0x7c000000); %bb.5(3.12%), %bb.3(96.88%)

  %33:anyregcls(s8) = HWTFPGA_EXTRACT %28:anyregcls(s19), 19, 8, 8
  %35:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %36:anyregcls(s1) = HWTFPGA_EXTRACT %35:anyregcls(s19), 19, 18, 1
  %37:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %33:anyregcls(s8), i3 2, 8, 8, 3
  HWTFPGA_CSTORE %37:anyregcls(s19), %0:anyregcls, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
  %47:anyregcls(s8) = HWTFPGA_EXTRACT %35:anyregcls(s19), 19, 8, 8
  %48:anyregcls(s1) = HWTFPGA_MUX i1 true
  %49:anyregcls(s19) = HWTFPGA_MUX %35:anyregcls(s19)
  %52:anyregcls(s1) = HWTFPGA_NOT %36:anyregcls(s1)
  HWTFPGA_BRCOND %52:anyregcls(s1), %bb.3

bb.5.blockL44i0_656:
; predecessors: %bb.3, %bb.4
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %41:anyregcls(s8) = HWTFPGA_EXTRACT %49:anyregcls(s19), 19, 0, 8
  %42:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %41:anyregcls(s8), i3 -2, 8, 8, 3
  HWTFPGA_CSTORE %42:anyregcls(s19), %0:anyregcls, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
  HWTFPGA_BR %bb.1

bb.6.blockL44i0_L738i0_738:
; predecessors: %bb.1, %bb.6
  successors: %bb.1(0x04000000), %bb.6(0x7c000000); %bb.1(3.12%), %bb.6(96.88%)

  %13:anyregcls(s19) = HWTFPGA_CLOAD %1:anyregcls, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
  %14:anyregcls(s1) = HWTFPGA_EXTRACT %13:anyregcls(s19), 19, 18, 1
  %50:anyregcls(s1) = HWTFPGA_NOT %14:anyregcls(s1)
  HWTFPGA_BRCOND %50:anyregcls(s1), %bb.6
  HWTFPGA_BR %bb.1

# End machine code for function EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop.

