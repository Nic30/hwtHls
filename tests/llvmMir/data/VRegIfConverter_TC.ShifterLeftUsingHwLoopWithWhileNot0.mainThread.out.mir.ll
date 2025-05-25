# Machine code for function ShifterLeftUsingHwLoopWithWhileNot0.mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.ShifterLeftUsingHwLoopWithWhileNot0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls = HWTFPGA_ARG_GET 2
  %5:anyregcls = G_CONSTANT i4 0
  %15:anyregcls = G_CONSTANT i3 0
  %23:anyregcls = G_CONSTANT i6 0
  %26:anyregcls = G_CONSTANT i5 0
  %33:anyregcls = G_CONSTANT i2 0
  %36:anyregcls = G_CONSTANT i1 false

bb.1.bb0:
; predecessors: %bb.0, %bb.6
  successors: %bb.5(0x80000000), %bb.2(0x40000000); %bb.5(100.00%), %bb.2(50.00%)

  %3:anyregcls = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
  %4:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 7
  %6:anyregcls = HWTFPGA_CLOAD %2:anyregcls, 0, 3, 1 :: (volatile load (s3) from %ir.sh, addrspace 3)
  %8:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 -4
  %29:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 4
  %30:anyregcls = HWTFPGA_MERGE_VALUES %15:anyregcls, killed %29:anyregcls, 3, 4
  %40:anyregcls = COPY killed %30:anyregcls
  %10:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 -3
  %27:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 3
  %28:anyregcls = HWTFPGA_MERGE_VALUES %5:anyregcls, killed %27:anyregcls, 4, 3
  %55:anyregcls = COPY killed %28:anyregcls
  %40:anyregcls = HWTFPGA_MUX %40:anyregcls, %8:anyregcls(s1), killed %55:anyregcls
  %57:anyregcls(s1) = G_CONSTANT i1 true
  %56:anyregcls(s1) = G_XOR killed %8:anyregcls, killed %57:anyregcls
  %59:anyregcls(s1) = G_CONSTANT i1 true
  %58:anyregcls(s1) = G_XOR killed %10:anyregcls, killed %59:anyregcls
  %60:anyregcls(s1) = G_AND killed %56:anyregcls, killed %58:anyregcls
  %12:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 -2
  %24:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 2
  %25:anyregcls = HWTFPGA_MERGE_VALUES %26:anyregcls, killed %24:anyregcls, 5, 2
  %63:anyregcls = COPY killed %25:anyregcls
  %14:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 -1
  %21:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 1
  %22:anyregcls = HWTFPGA_MERGE_VALUES %23:anyregcls, killed %21:anyregcls, 6, 1
  %49:anyregcls = COPY killed %22:anyregcls
  %63:anyregcls = HWTFPGA_MUX %63:anyregcls, %12:anyregcls(s1), killed %49:anyregcls
  %51:anyregcls(s1) = G_CONSTANT i1 true
  %50:anyregcls(s1) = G_XOR killed %12:anyregcls, killed %51:anyregcls
  %53:anyregcls(s1) = G_CONSTANT i1 true
  %52:anyregcls(s1) = G_XOR killed %14:anyregcls, killed %53:anyregcls
  %54:anyregcls(s1) = G_AND killed %50:anyregcls, killed %52:anyregcls
  %40:anyregcls = HWTFPGA_MUX killed %63:anyregcls, %60:anyregcls(s1), %40:anyregcls
  %64:anyregcls(s1) = G_AND killed %60:anyregcls, killed %54:anyregcls
  G_BRCOND killed %64:anyregcls(s1), %bb.2
  G_BR %bb.5

bb.2.bb0:
; predecessors: %bb.1
  successors: %bb.6(0x20000000), %bb.3(0x60000000); %bb.6(25.00%), %bb.3(75.00%)

  %16:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 0
  %41:anyregcls = COPY %3:anyregcls
  G_BRCOND killed %16:anyregcls(s1), %bb.6

bb.3.bb0:
; predecessors: %bb.2
  successors: %bb.5(0x2aaaaaab), %bb.4(0x55555555); %bb.5(33.33%), %bb.4(66.67%)

  %18:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls, i3 1
  %40:anyregcls = COPY killed %4:anyregcls
  G_BRCOND killed %18:anyregcls(s1), %bb.5

bb.4.bb0:
; predecessors: %bb.3
  successors: %bb.5(0x80000000); %bb.5(100.00%)

  %20:anyregcls(s1) = G_ICMP intpred(eq), killed %6:anyregcls, i3 2
  %34:anyregcls = HWTFPGA_EXTRACT %3:anyregcls, 8, 0, 6
  %35:anyregcls = HWTFPGA_MERGE_VALUES %36:anyregcls, killed %34:anyregcls, 1, 6
  %40:anyregcls = COPY killed %35:anyregcls
  %31:anyregcls = HWTFPGA_EXTRACT killed %3:anyregcls, 8, 0, 5
  %32:anyregcls = HWTFPGA_MERGE_VALUES %33:anyregcls, killed %31:anyregcls, 2, 5
  %48:anyregcls = COPY killed %32:anyregcls
  %40:anyregcls = HWTFPGA_MUX killed %40:anyregcls, killed %20:anyregcls(s1), killed %48:anyregcls

bb.5.bb.loopexit:
; predecessors: %bb.3, %bb.4, %bb.1
  successors: %bb.6(0x80000000); %bb.6(100.00%)

  %37:anyregcls = COPY killed %40:anyregcls
  %38:anyregcls = HWTFPGA_MERGE_VALUES %36:anyregcls, killed %37:anyregcls, 1, 7
  %41:anyregcls = COPY killed %38:anyregcls

bb.6.bb:
; predecessors: %bb.2, %bb.5
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %39:anyregcls = COPY killed %41:anyregcls
  HWTFPGA_CSTORE killed %39:anyregcls, %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.1

# End machine code for function ShifterLeftUsingHwLoopWithWhileNot0.mainThread.

