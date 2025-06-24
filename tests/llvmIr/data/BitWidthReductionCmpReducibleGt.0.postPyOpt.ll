define void @"BitWidthReductionCmpReducibleEq.hwImpl.<locals>.mainThread"(ptr addrspace(1) %a, ptr addrspace(2) %b, ptr addrspace(3) %res, ptr addrspace(4) %res_prefix_0vs1, ptr addrspace(5) %res_prefix_0vsAll, ptr addrspace(6) %res_prefix_aVs0, ptr addrspace(7) %res_prefix_aVsAll, ptr addrspace(8) %res_prefix_bVs0, ptr addrspace(9) %res_prefix_bVsAll, ptr addrspace(10) %res_prefix_differentInMiddle, ptr addrspace(11) %res_prefix_same, ptr addrspace(12) %res_prefix_sameInMiddle, ptr addrspace(13) %res_prefix_same_1, ptr addrspace(14) %res_same, ptr addrspace(15) %res_suffix_0vsB, ptr addrspace(16) %res_suffix_AllVsB, ptr addrspace(17) %res_suffix_aVs0, ptr addrspace(18) %res_suffix_aVsAll) !hwtHls.io !0 {
bb0:
  br label %entry

entry:                                            ; preds = %bb0
  br label %loopHeader

loopHeader:                                       ; preds = %blockL40i0_1958, %entry
  %a_read = alloca i8, align 1, !hwtHls.tmp.alloca !20
  store i8 undef, ptr %a_read, align 1
  %a1 = alloca i8, align 1, !hwtHls.tmp.alloca !20
  store i8 undef, ptr %a1, align 1
  %a_read2 = load volatile i8, ptr addrspace(1) %a, align 1
  store i8 %a_read2, ptr %a_read, align 1
  %a_read3 = load i8, ptr %a_read, align 1
  %0 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %a_read3, i4 0) #1
  %1 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %a_read3, i4 4) #1
  store i8 %a_read3, ptr %a1, align 1
  %b_read = alloca i8, align 1, !hwtHls.tmp.alloca !20
  store i8 undef, ptr %b_read, align 1
  %b1 = alloca i8, align 1, !hwtHls.tmp.alloca !20
  store i8 undef, ptr %b1, align 1
  %b_read2 = load volatile i8, ptr addrspace(2) %b, align 1
  store i8 %b_read2, ptr %b_read, align 1
  %b_read3 = load i8, ptr %b_read, align 1
  %2 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %b_read3, i4 0) #1
  %3 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %b_read3, i4 4) #1
  store i8 %b_read3, ptr %b1, align 1
  %4 = icmp ugt i8 %a_read3, %b_read3
  store volatile i1 %4, ptr addrspace(3) %res, align 1
  store volatile i1 false, ptr addrspace(14) %res_same, align 1
  %5 = zext i8 %a_read3 to i16
  %6 = zext i8 %b_read3 to i16
  %7 = icmp ugt i16 %5, %6
  store volatile i1 %7, ptr addrspace(11) %res_prefix_same, align 1
  %8 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read3, i8 1) #1
  %9 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read3, i8 1) #1
  %10 = icmp ugt i16 %8, %9
  store volatile i1 %10, ptr addrspace(13) %res_prefix_same_1, align 1
  %11 = icmp ugt i16 %5, %9
  store volatile i1 %11, ptr addrspace(4) %res_prefix_0vs1, align 1
  %12 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read3, i8 -1) #1
  %13 = icmp ugt i16 %5, %12
  store volatile i1 %13, ptr addrspace(5) %res_prefix_0vsAll, align 1
  %14 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read3, i8 %a_read3) #1
  %15 = icmp ugt i16 %14, %6
  store volatile i1 %15, ptr addrspace(17) %res_suffix_aVs0, align 1
  %16 = icmp ugt i16 %14, %12
  store volatile i1 %16, ptr addrspace(18) %res_suffix_aVsAll, align 1
  %17 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read3, i8 %b_read3) #1
  %18 = icmp ugt i16 %5, %17
  store volatile i1 %18, ptr addrspace(15) %res_suffix_0vsB, align 1
  %19 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read3, i8 -1) #1
  %20 = icmp ugt i16 %19, %17
  store volatile i1 %20, ptr addrspace(16) %res_suffix_AllVsB, align 1
  %21 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %b_read3) #1
  %22 = icmp ugt i16 %14, %21
  store volatile i1 %22, ptr addrspace(6) %res_prefix_aVs0, align 1
  %23 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %b_read3) #1
  %24 = icmp ugt i16 %14, %23
  store volatile i1 %24, ptr addrspace(7) %res_prefix_aVsAll, align 1
  %25 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %a_read3) #1
  %26 = icmp ugt i16 %25, %17
  store volatile i1 %26, ptr addrspace(8) %res_prefix_bVs0, align 1
  %27 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %a_read3) #1
  %28 = icmp ugt i16 %27, %17
  store volatile i1 %28, ptr addrspace(9) %res_prefix_bVsAll, align 1
  %29 = call i12 @hwtHls.bitConcat.i8.i4(i8 0, i4 %1) #1
  %30 = call i16 @hwtHls.bitConcat.i4.i12(i4 %0, i12 %29) #1
  %31 = call i12 @hwtHls.bitConcat.i8.i4(i8 0, i4 %3) #1
  %32 = call i16 @hwtHls.bitConcat.i4.i12(i4 %2, i12 %31) #1
  %33 = icmp ugt i16 %30, %32
  store volatile i1 %33, ptr addrspace(12) %res_prefix_sameInMiddle, align 1
  %34 = call i12 @hwtHls.bitConcat.i8.i4(i8 -1, i4 %3) #1
  %35 = call i16 @hwtHls.bitConcat.i4.i12(i4 %2, i12 %34) #1
  %36 = icmp ugt i16 %30, %35
  store volatile i1 %36, ptr addrspace(10) %res_prefix_differentInMiddle, align 1
  br label %blockL40i0_1958

blockL40i0_1958:                                  ; preds = %loopHeader
  br label %loopHeader
}
