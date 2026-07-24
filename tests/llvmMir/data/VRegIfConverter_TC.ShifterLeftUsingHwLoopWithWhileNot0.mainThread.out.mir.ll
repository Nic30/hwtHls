# Machine code for function ShifterLeftUsingHwLoopWithWhileNot0.mainThread: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.ShifterLeftUsingHwLoopWithWhileNot0.mainThread:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1
  %2:anyregcls = HWTFPGA_ARG_GET 2
  %5:anyregcls(s4) = G_CONSTANT i4 0
  %15:anyregcls(s3) = G_CONSTANT i3 0
  %23:anyregcls(s6) = G_CONSTANT i6 0
  %26:anyregcls(s5) = G_CONSTANT i5 0
  %33:anyregcls(s2) = G_CONSTANT i2 0
  %36:anyregcls(s1) = G_CONSTANT i1 false

bb.1.bb0:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %3:anyregcls(s8) = HWTFPGA_CLOAD %0:anyregcls, 0, 8, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
  %4:anyregcls(s7) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 7
  %6:anyregcls(s3) = HWTFPGA_CLOAD %2:anyregcls, 0, 3, 1 :: (volatile load (s3) from %ir.sh, addrspace 3)
  %8:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 -4
  %29:anyregcls(s4) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 4
  %30:anyregcls(s7) = HWTFPGA_MERGE_VALUES %15:anyregcls(s3), killed %29:anyregcls(s4), 3, 4
  %40:anyregcls(s7) = COPY killed %30:anyregcls(s7)
  %10:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 -3
  %27:anyregcls(s3) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 3
  %28:anyregcls(s7) = HWTFPGA_MERGE_VALUES %5:anyregcls(s4), killed %27:anyregcls(s3), 4, 3
  %55:anyregcls(s7) = COPY killed %28:anyregcls(s7)
  %40:anyregcls(s7) = HWTFPGA_MUX killed %40:anyregcls(s7), %8:anyregcls(s1), killed %55:anyregcls(s7)
  %57:anyregcls(s1) = G_CONSTANT i1 true
  %56:anyregcls(s1) = G_XOR killed %8:anyregcls, killed %57:anyregcls
  %59:anyregcls(s1) = G_CONSTANT i1 true
  %58:anyregcls(s1) = G_XOR killed %10:anyregcls, killed %59:anyregcls
  %60:anyregcls(s1) = G_AND killed %56:anyregcls, killed %58:anyregcls
  %12:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 -2
  %24:anyregcls(s2) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 2
  %25:anyregcls(s7) = HWTFPGA_MERGE_VALUES %26:anyregcls(s5), killed %24:anyregcls(s2), 5, 2
  %63:anyregcls(s7) = COPY killed %25:anyregcls(s7)
  %14:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 -1
  %21:anyregcls(s1) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 1
  %22:anyregcls(s7) = HWTFPGA_MERGE_VALUES %23:anyregcls(s6), killed %21:anyregcls(s1), 6, 1
  %49:anyregcls(s7) = COPY killed %22:anyregcls(s7)
  %63:anyregcls(s7) = HWTFPGA_MUX killed %63:anyregcls(s7), %12:anyregcls(s1), killed %49:anyregcls(s7)
  %51:anyregcls(s1) = G_CONSTANT i1 true
  %50:anyregcls(s1) = G_XOR killed %12:anyregcls, killed %51:anyregcls
  %53:anyregcls(s1) = G_CONSTANT i1 true
  %52:anyregcls(s1) = G_XOR killed %14:anyregcls, killed %53:anyregcls
  %54:anyregcls(s1) = G_AND killed %50:anyregcls, killed %52:anyregcls
  %40:anyregcls(s7) = HWTFPGA_MUX killed %63:anyregcls(s7), %60:anyregcls(s1), killed %40:anyregcls(s7)
  %64:anyregcls(s1) = G_AND killed %60:anyregcls, killed %54:anyregcls
  %65:anyregcls(s1) = HWTFPGA_MUX i1 false
  %69:anyregcls(s1) = HWTFPGA_MUX i1 false
  %16:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 0
  %41:anyregcls(s8) = COPY %3:anyregcls(s8)
  %74:anyregcls(s7) = HWTFPGA_IMPLICIT_DEF 7
  %75:anyregcls(s1) = HWTFPGA_IMPLICIT_DEF 1
  %71:anyregcls(s1) = G_CONSTANT i1 true
  %70:anyregcls(s1) = G_XOR %16:anyregcls, killed %71:anyregcls
  %76:anyregcls(s1) = HWTFPGA_MUX killed %70:anyregcls(s1)
  %40:anyregcls(s7) = HWTFPGA_MUX killed %74:anyregcls(s7), %64:anyregcls(s1), killed %40:anyregcls(s7)
  %65:anyregcls(s1) = HWTFPGA_MUX killed %75:anyregcls(s1), %64:anyregcls(s1), killed %65:anyregcls(s1)
  %69:anyregcls(s1) = HWTFPGA_MUX killed %76:anyregcls(s1), %64:anyregcls(s1), killed %69:anyregcls(s1)
  %77:anyregcls(s1) = G_AND killed %64:anyregcls, killed %16:anyregcls
  %18:anyregcls(s1) = G_ICMP intpred(eq), %6:anyregcls(s3), i3 1
  %72:anyregcls(s7) = COPY killed %4:anyregcls(s7)
  %67:anyregcls(s1) = G_CONSTANT i1 true
  %66:anyregcls(s1) = G_XOR killed %18:anyregcls, killed %67:anyregcls
  %73:anyregcls(s1) = HWTFPGA_MUX killed %66:anyregcls(s1)
  %40:anyregcls(s7) = HWTFPGA_MUX killed %72:anyregcls(s7), %69:anyregcls(s1), killed %40:anyregcls(s7)
  %65:anyregcls(s1) = HWTFPGA_MUX killed %73:anyregcls(s1), killed %69:anyregcls(s1), killed %65:anyregcls(s1)
  %20:anyregcls(s1) = G_ICMP intpred(eq), killed %6:anyregcls(s3), i3 2
  %34:anyregcls(s6) = HWTFPGA_EXTRACT %3:anyregcls(s8), 8, 0, 6
  %35:anyregcls(s7) = HWTFPGA_MERGE_VALUES %36:anyregcls(s1), killed %34:anyregcls(s6), 1, 6
  %68:anyregcls(s7) = COPY killed %35:anyregcls(s7)
  %31:anyregcls(s5) = HWTFPGA_EXTRACT killed %3:anyregcls(s8), 8, 0, 5
  %32:anyregcls(s7) = HWTFPGA_MERGE_VALUES %33:anyregcls(s2), killed %31:anyregcls(s5), 2, 5
  %48:anyregcls(s7) = COPY killed %32:anyregcls(s7)
  %68:anyregcls(s7) = HWTFPGA_MUX killed %68:anyregcls(s7), killed %20:anyregcls(s1), killed %48:anyregcls(s7)
  %40:anyregcls(s7) = HWTFPGA_MUX killed %68:anyregcls(s7), killed %65:anyregcls(s1), killed %40:anyregcls(s7)
  %37:anyregcls(s7) = COPY killed %40:anyregcls(s7)
  %38:anyregcls(s8) = HWTFPGA_MERGE_VALUES %36:anyregcls(s1), killed %37:anyregcls(s7), 1, 7
  %78:anyregcls(s8) = COPY killed %38:anyregcls(s8)
  %41:anyregcls(s8) = HWTFPGA_MUX killed %41:anyregcls(s8), killed %77:anyregcls(s1), killed %78:anyregcls(s8)
  %39:anyregcls(s8) = COPY killed %41:anyregcls(s8)
  HWTFPGA_CSTORE killed %39:anyregcls(s8), %1:anyregcls, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
  G_BR %bb.1

# End machine code for function ShifterLeftUsingHwLoopWithWhileNot0.mainThread.

