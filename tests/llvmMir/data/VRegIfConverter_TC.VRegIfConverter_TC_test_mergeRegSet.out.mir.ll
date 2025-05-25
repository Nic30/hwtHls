# Machine code for function VRegIfConverter_TC_test_mergeRegSet: NoPHIs, TracksLiveness, Legalized, RegBankSelected, Selected

bb.0.test_mergeRegSet:
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %0:anyregcls = HWTFPGA_ARG_GET 0
  %1:anyregcls = HWTFPGA_ARG_GET 1

bb.1.blockL42i0_42:
; predecessors: %bb.0, %bb.1
  successors: %bb.1(0x80000000); %bb.1(100.00%)

  %2:anyregcls(s16) = HWTFPGA_CLOAD %0:anyregcls, 0, 16, 1 :: (volatile load (s16) from %ir.a, addrspace 1)
  %4:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %2:anyregcls(s16), i16 0
  %129:anyregcls(s16) = HWTFPGA_MUX i16 0
  %130:anyregcls(s12) = HWTFPGA_MUX i12 0
  %5:anyregcls(s1) = HWTFPGA_EXTRACT %2:anyregcls(s16), 16, 15, 1
  %7:anyregcls(s16) = HWTFPGA_SUB i16 0, %2:anyregcls(s16)
  %8:anyregcls(s16) = HWTFPGA_MUX killed %7:anyregcls(s16), %5:anyregcls(s1), killed %2:anyregcls(s16)
  %9:anyregcls(s1) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 1
  %11:anyregcls(s2) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 2
  %12:anyregcls(s3) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 3
  %13:anyregcls(s4) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 4
  %14:anyregcls(s5) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 5
  %15:anyregcls(s6) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 6
  %16:anyregcls(s7) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 7
  %17:anyregcls(s8) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 8
  %18:anyregcls(s9) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 9
  %19:anyregcls(s10) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 10
  %20:anyregcls(s11) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 11
  %21:anyregcls(s12) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 12
  %22:anyregcls(s13) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 13
  %23:anyregcls(s14) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 14
  %24:anyregcls(s15) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 0, 15
  %25:anyregcls(s8) = HWTFPGA_EXTRACT %8:anyregcls(s16), 16, 8, 8
  %28:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %25:anyregcls(s8), i8 0
  %29:anyregcls(s8) = HWTFPGA_MUX %17:anyregcls(s8), %28:anyregcls(s1), killed %25:anyregcls(s8)
  %30:anyregcls(s4) = HWTFPGA_EXTRACT %29:anyregcls(s8), 8, 4, 4
  %33:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %30:anyregcls(s4), i4 0
  %34:anyregcls(s4) = HWTFPGA_EXTRACT killed %29:anyregcls(s8), 8, 0, 4
  %35:anyregcls(s4) = HWTFPGA_MUX killed %34:anyregcls(s4), %33:anyregcls(s1), killed %30:anyregcls(s4)
  %36:anyregcls(s2) = HWTFPGA_EXTRACT %35:anyregcls(s4), 4, 2, 2
  %39:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %36:anyregcls(s2), i2 0
  %40:anyregcls(s2) = HWTFPGA_EXTRACT killed %35:anyregcls(s4), 4, 0, 2
  %42:anyregcls(s2) = HWTFPGA_MUX killed %40:anyregcls(s2), %39:anyregcls(s1), killed %36:anyregcls(s2)
  %43:anyregcls(s1) = HWTFPGA_EXTRACT killed %42:anyregcls(s2), 2, 1, 1
  %46:anyregcls(s1) = HWTFPGA_NOT killed %43:anyregcls(s1)
  %47:anyregcls(s11) = HWTFPGA_MERGE_VALUES %46:anyregcls(s1), %39:anyregcls(s1), %33:anyregcls(s1), %28:anyregcls(s1), i7 0, 1, 1, 1, 1, 7
  %50:anyregcls(s11) = HWTFPGA_SUB i11 -1010, killed %47:anyregcls(s11)
  %51:anyregcls(s4) = HWTFPGA_MERGE_VALUES killed %46:anyregcls(s1), killed %39:anyregcls(s1), killed %33:anyregcls(s1), killed %28:anyregcls(s1), 1, 1, 1, 1
  %53:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -1
  %55:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -2
  %57:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -3
  %59:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -4
  %61:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -5
  %63:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -6
  %65:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -7
  %67:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 -8
  %69:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 7
  %71:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 6
  %73:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 5
  %74:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 4
  %76:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 3
  %78:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 2
  %80:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51:anyregcls(s4), i4 1
  %81:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), killed %51:anyregcls(s4), i4 0
  %83:anyregcls(s16) = HWTFPGA_MERGE_VALUES i1 false, killed %24:anyregcls(s15), 1, 15
  %86:anyregcls(s16) = HWTFPGA_MERGE_VALUES i2 0, killed %23:anyregcls(s14), 2, 14
  %88:anyregcls(s16) = HWTFPGA_MERGE_VALUES i3 0, killed %22:anyregcls(s13), 3, 13
  %90:anyregcls(s16) = HWTFPGA_MERGE_VALUES i4 0, killed %21:anyregcls(s12), 4, 12
  %92:anyregcls(s16) = HWTFPGA_MERGE_VALUES i5 0, killed %20:anyregcls(s11), 5, 11
  %94:anyregcls(s16) = HWTFPGA_MERGE_VALUES i6 0, killed %19:anyregcls(s10), 6, 10
  %97:anyregcls(s16) = HWTFPGA_MERGE_VALUES i7 0, killed %18:anyregcls(s9), 7, 9
  %99:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, killed %17:anyregcls(s8), 8, 8
  %101:anyregcls(s16) = HWTFPGA_MERGE_VALUES i9 0, killed %16:anyregcls(s7), 9, 7
  %104:anyregcls(s16) = HWTFPGA_MERGE_VALUES i10 0, killed %15:anyregcls(s6), 10, 6
  %107:anyregcls(s16) = HWTFPGA_MERGE_VALUES i11 0, killed %14:anyregcls(s5), 11, 5
  %110:anyregcls(s16) = HWTFPGA_MERGE_VALUES i12 0, killed %13:anyregcls(s4), 12, 4
  %113:anyregcls(s16) = HWTFPGA_MERGE_VALUES i13 0, killed %12:anyregcls(s3), 13, 3
  %116:anyregcls(s16) = HWTFPGA_MERGE_VALUES i14 0, killed %11:anyregcls(s2), 14, 2
  %119:anyregcls(s16) = HWTFPGA_MERGE_VALUES i15 0, killed %9:anyregcls(s1), 15, 1
  %131:anyregcls(s16) = HWTFPGA_MUX killed %119:anyregcls(s16), killed %53:anyregcls(s1), killed %116:anyregcls(s16), killed %55:anyregcls(s1), killed %113:anyregcls(s16), killed %57:anyregcls(s1), killed %110:anyregcls(s16), killed %59:anyregcls(s1), killed %107:anyregcls(s16), killed %61:anyregcls(s1), killed %104:anyregcls(s16), killed %63:anyregcls(s1), killed %101:anyregcls(s16), killed %65:anyregcls(s1), killed %99:anyregcls(s16), killed %67:anyregcls(s1), killed %97:anyregcls(s16), killed %69:anyregcls(s1), killed %94:anyregcls(s16), killed %71:anyregcls(s1), killed %92:anyregcls(s16), killed %73:anyregcls(s1), killed %90:anyregcls(s16), killed %74:anyregcls(s1), killed %88:anyregcls(s16), killed %76:anyregcls(s1), killed %86:anyregcls(s16), killed %78:anyregcls(s1), killed %83:anyregcls(s16), killed %80:anyregcls(s1), killed %8:anyregcls(s16), killed %81:anyregcls(s1), i16 0
  %132:anyregcls(s12) = HWTFPGA_MERGE_VALUES killed %50:anyregcls(s11), killed %5:anyregcls(s1), 11, 1
  %129:anyregcls(s16) = HWTFPGA_MUX killed %131:anyregcls(s16), %4:anyregcls(s1), killed %129:anyregcls(s16)
  %130:anyregcls(s12) = HWTFPGA_MUX killed %132:anyregcls(s12), killed %4:anyregcls(s1), killed %130:anyregcls(s12)
  %125:anyregcls(s64) = HWTFPGA_MERGE_VALUES killed %129:anyregcls(s16), i36 0, killed %130:anyregcls(s12), 16, 36, 12
  HWTFPGA_CSTORE killed %125:anyregcls(s64), %1:anyregcls, 0, 64, 1 :: (volatile store (s64) into %ir.res, align 4, addrspace 2)
  G_BR %bb.1

# End machine code for function VRegIfConverter_TC_test_mergeRegSet.

