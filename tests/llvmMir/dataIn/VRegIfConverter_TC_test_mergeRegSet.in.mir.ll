--- |
  ; ModuleID = 'VRegIfConverter_TC_test_mergeRegSet'
  source_filename = "VRegIfConverter_TC_test_mergeRegSet"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @VRegIfConverter_TC_test_mergeRegSet(ptr addrspace(1) %a, ptr addrspace(2) %res) !hwtHls.param_addr_width !0 {
  test_mergeRegSet:
    br label %blockL42i0_42
  
  blockL42i0_42:                                    ; preds = %test_mergeRegSet, %blockL42i0_42_afterCall
    %"a0(a_read)" = load volatile i16, ptr addrspace(1) %a, align 2
    %"229" = icmp eq i16 %"a0(a_read)", 0
    br i1 %"229", label %blockL42i0_42_afterCall, label %"blockL42i0__IEEE754FpFromInt_152__416"
  
  blockL42i0_42_afterCall:                          ; preds = %"blockL42i0__IEEE754FpFromInt_152__416", %blockL42i0_42
    %"%212(res_mantissa)3" = phi i16 [ 0, %blockL42i0_42 ], [ %71, %"blockL42i0__IEEE754FpFromInt_152__416" ]
    %.phiConc = phi i12 [ 0, %blockL42i0_42 ], [ %72, %"blockL42i0__IEEE754FpFromInt_152__416" ]
    %0 = call i64 @hwtHls.bitConcat.i16.i36.i12(i16 %"%212(res_mantissa)3", i36 0, i12 %.phiConc) #1
    store volatile i64 %0, ptr addrspace(2) %res, align 4
    br label %blockL42i0_42
  
  "blockL42i0__IEEE754FpFromInt_152__416":         ; preds = %blockL42i0_42
    %1 = call i1 @hwtHls.bitRangeGet.i16.i5.i1.15(i16 %"a0(a_read)", i5 15) #1
    %"7" = sub i16 0, %"a0(a_read)"
    %"8" = select i1 %1, i16 %"7", i16 %"a0(a_read)"
    %2 = call i1 @hwtHls.bitRangeGet.i16.i5.i1.0(i16 %"8", i5 0) #1
    %3 = call i2 @hwtHls.bitRangeGet.i16.i5.i2.0(i16 %"8", i5 0) #1
    %4 = call i3 @hwtHls.bitRangeGet.i16.i5.i3.0(i16 %"8", i5 0) #1
    %5 = call i4 @hwtHls.bitRangeGet.i16.i5.i4.0(i16 %"8", i5 0) #1
    %6 = call i5 @hwtHls.bitRangeGet.i16.i5.i5.0(i16 %"8", i5 0) #1
    %7 = call i6 @hwtHls.bitRangeGet.i16.i5.i6.0(i16 %"8", i5 0) #1
    %8 = call i7 @hwtHls.bitRangeGet.i16.i5.i7.0(i16 %"8", i5 0) #1
    %9 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %"8", i5 0) #1
    %10 = call i9 @hwtHls.bitRangeGet.i16.i5.i9.0(i16 %"8", i5 0) #1
    %11 = call i10 @hwtHls.bitRangeGet.i16.i5.i10.0(i16 %"8", i5 0) #1
    %12 = call i11 @hwtHls.bitRangeGet.i16.i5.i11.0(i16 %"8", i5 0) #1
    %13 = call i12 @hwtHls.bitRangeGet.i16.i5.i12.0(i16 %"8", i5 0) #1
    %14 = call i13 @hwtHls.bitRangeGet.i16.i5.i13.0(i16 %"8", i5 0) #1
    %15 = call i14 @hwtHls.bitRangeGet.i16.i5.i14.0(i16 %"8", i5 0) #1
    %16 = call i15 @hwtHls.bitRangeGet.i16.i5.i15.0(i16 %"8", i5 0) #1
    %17 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16 %"8", i5 8) #1
    %"16(leftFull)612" = icmp eq i8 %17, 0
    %"%57(in_)" = select i1 %"16(leftFull)612", i8 %9, i8 %17
    %18 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %"%57(in_)", i4 4) #1
    %"23(leftFull)713" = icmp eq i4 %18, 0
    %19 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %"%57(in_)", i4 0) #1
    %"%46(in_)" = select i1 %"23(leftFull)713", i4 %19, i4 %18
    %20 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %"%46(in_)", i3 2) #1
    %"30(leftFull)814" = icmp eq i2 %20, 0
    %21 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %"%46(in_)", i3 0) #1
    %"%36(in_)" = select i1 %"30(leftFull)814", i2 %21, i2 %20
    %22 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %"%36(in_)", i2 1) #1
    %"35(halfCount)" = xor i1 %22, true
    %23 = call i11 @hwtHls.bitConcat.i1.i1.i1.i1.i7(i1 %"35(halfCount)", i1 %"30(leftFull)814", i1 %"23(leftFull)713", i1 %"16(leftFull)612", i7 0) #1
    %"192" = sub nuw i11 -1010, %23
    %24 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %"35(halfCount)", i1 %"30(leftFull)814", i1 %"23(leftFull)713", i1 %"16(leftFull)612") #1
    %25 = icmp eq i4 %24, -1
    %26 = icmp eq i4 %24, -2
    %27 = icmp eq i4 %24, -3
    %28 = icmp eq i4 %24, -4
    %29 = icmp eq i4 %24, -5
    %30 = icmp eq i4 %24, -6
    %31 = icmp eq i4 %24, -7
    %32 = icmp eq i4 %24, -8
    %33 = icmp eq i4 %24, 7
    %34 = icmp eq i4 %24, 6
    %35 = icmp eq i4 %24, 5
    %36 = icmp eq i4 %24, 4
    %37 = icmp eq i4 %24, 3
    %38 = icmp eq i4 %24, 2
    %39 = icmp eq i4 %24, 1
    %40 = icmp eq i4 %24, 0
    %41 = select i1 %40, i16 %"8", i16 0
    %42 = call i16 @hwtHls.bitConcat.i1.i15(i1 false, i15 %16) #1
    %43 = select i1 %39, i16 %42, i16 %41
    %44 = call i16 @hwtHls.bitConcat.i2.i14(i2 0, i14 %15) #1
    %45 = select i1 %38, i16 %44, i16 %43
    %46 = call i16 @hwtHls.bitConcat.i3.i13(i3 0, i13 %14) #1
    %47 = select i1 %37, i16 %46, i16 %45
    %48 = call i16 @hwtHls.bitConcat.i4.i12(i4 0, i12 %13) #1
    %49 = select i1 %36, i16 %48, i16 %47
    %50 = call i16 @hwtHls.bitConcat.i5.i11(i5 0, i11 %12) #1
    %51 = select i1 %35, i16 %50, i16 %49
    %52 = call i16 @hwtHls.bitConcat.i6.i10(i6 0, i10 %11) #1
    %53 = select i1 %34, i16 %52, i16 %51
    %54 = call i16 @hwtHls.bitConcat.i7.i9(i7 0, i9 %10) #1
    %55 = select i1 %33, i16 %54, i16 %53
    %56 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %9) #1
    %57 = select i1 %32, i16 %56, i16 %55
    %58 = call i16 @hwtHls.bitConcat.i9.i7(i9 0, i7 %8) #1
    %59 = select i1 %31, i16 %58, i16 %57
    %60 = call i16 @hwtHls.bitConcat.i10.i6(i10 0, i6 %7) #1
    %61 = select i1 %30, i16 %60, i16 %59
    %62 = call i16 @hwtHls.bitConcat.i11.i5(i11 0, i5 %6) #1
    %63 = select i1 %29, i16 %62, i16 %61
    %64 = call i16 @hwtHls.bitConcat.i12.i4(i12 0, i4 %5) #1
    %65 = select i1 %28, i16 %64, i16 %63
    %66 = call i16 @hwtHls.bitConcat.i13.i3(i13 0, i3 %4) #1
    %67 = select i1 %27, i16 %66, i16 %65
    %68 = call i16 @hwtHls.bitConcat.i14.i2(i14 0, i2 %3) #1
    %69 = select i1 %26, i16 %68, i16 %67
    %70 = call i16 @hwtHls.bitConcat.i15.i1(i15 0, i1 %2) #1
    %71 = select i1 %25, i16 %70, i16 %69
    %72 = call i12 @hwtHls.bitConcat.i11.i1(i11 %"192", i1 %1) #1
    br label %blockL42i0_42_afterCall
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i16.i5.i1.15(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitRangeGet.i16.i5.i8.8(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i15 @hwtHls.bitRangeGet.i16.i5.i15.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i1.i15(i1, i15) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i11 @hwtHls.bitConcat.i1.i1.i1.i1.i7(i1, i1, i1, i1, i7) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1, i1, i1, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i14 @hwtHls.bitRangeGet.i16.i5.i14.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i2.i14(i2, i14) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i13 @hwtHls.bitRangeGet.i16.i5.i13.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i3.i13(i3, i13) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i12 @hwtHls.bitRangeGet.i16.i5.i12.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i4.i12(i4, i12) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i11 @hwtHls.bitRangeGet.i16.i5.i11.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i5.i11(i5, i11) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i10 @hwtHls.bitRangeGet.i16.i5.i10.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i6.i10(i6, i10) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i9 @hwtHls.bitRangeGet.i16.i5.i9.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i7.i9(i7, i9) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i7 @hwtHls.bitRangeGet.i16.i5.i7.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i9.i7(i9, i7) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i6 @hwtHls.bitRangeGet.i16.i5.i6.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i10.i6(i10, i6) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i5 @hwtHls.bitRangeGet.i16.i5.i5.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i11.i5(i11, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitRangeGet.i16.i5.i4.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i12.i4(i12, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i3 @hwtHls.bitRangeGet.i16.i5.i3.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i13.i3(i13, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i16.i5.i2.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i14.i2(i14, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i16.i5.i1.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i15.i1(i15, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i12 @hwtHls.bitConcat.i11.i1(i11, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i64 @hwtHls.bitConcat.i16.i36.i12(i16, i36, i12) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}

...
---
name:            VRegIfConverter_TC_test_mergeRegSet
alignment:       1
exposesReturnsTwice: false
legalized:       true
regBankSelected: true
selected:        true
failedISel:      false
tracksRegLiveness: true
hasWinCFI:       false
callsEHReturn:   false
callsUnwindInit: false
hasEHCatchret:   false
hasEHScopes:     false
hasEHFunclets:   false
isOutlined:      false
debugInstrRef:   false
failsVerification: false
tracksDebugUserValues: false
registers:
  - { id: 0, class: anyregcls, preferred-register: '' }
  - { id: 1, class: anyregcls, preferred-register: '' }
  - { id: 2, class: anyregcls, preferred-register: '' }
  - { id: 3, class: anyregcls, preferred-register: '' }
  - { id: 4, class: anyregcls, preferred-register: '' }
  - { id: 5, class: anyregcls, preferred-register: '' }
  - { id: 6, class: _, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
  - { id: 16, class: anyregcls, preferred-register: '' }
  - { id: 17, class: anyregcls, preferred-register: '' }
  - { id: 18, class: anyregcls, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregcls, preferred-register: '' }
  - { id: 21, class: anyregcls, preferred-register: '' }
  - { id: 22, class: anyregcls, preferred-register: '' }
  - { id: 23, class: anyregcls, preferred-register: '' }
  - { id: 24, class: anyregcls, preferred-register: '' }
  - { id: 25, class: anyregcls, preferred-register: '' }
  - { id: 26, class: _, preferred-register: '' }
  - { id: 27, class: anyregcls, preferred-register: '' }
  - { id: 28, class: anyregcls, preferred-register: '' }
  - { id: 29, class: anyregcls, preferred-register: '' }
  - { id: 30, class: anyregcls, preferred-register: '' }
  - { id: 31, class: anyregbank, preferred-register: '' }
  - { id: 32, class: anyregcls, preferred-register: '' }
  - { id: 33, class: anyregcls, preferred-register: '' }
  - { id: 34, class: anyregcls, preferred-register: '' }
  - { id: 35, class: anyregcls, preferred-register: '' }
  - { id: 36, class: anyregcls, preferred-register: '' }
  - { id: 37, class: _, preferred-register: '' }
  - { id: 38, class: anyregcls, preferred-register: '' }
  - { id: 39, class: anyregcls, preferred-register: '' }
  - { id: 40, class: anyregcls, preferred-register: '' }
  - { id: 41, class: anyregcls, preferred-register: '' }
  - { id: 42, class: anyregcls, preferred-register: '' }
  - { id: 43, class: anyregcls, preferred-register: '' }
  - { id: 44, class: _, preferred-register: '' }
  - { id: 45, class: anyregbank, preferred-register: '' }
  - { id: 46, class: anyregcls, preferred-register: '' }
  - { id: 47, class: anyregcls, preferred-register: '' }
  - { id: 48, class: anyregcls, preferred-register: '' }
  - { id: 49, class: anyregbank, preferred-register: '' }
  - { id: 50, class: anyregcls, preferred-register: '' }
  - { id: 51, class: anyregcls, preferred-register: '' }
  - { id: 52, class: anyregbank, preferred-register: '' }
  - { id: 53, class: anyregcls, preferred-register: '' }
  - { id: 54, class: anyregbank, preferred-register: '' }
  - { id: 55, class: anyregcls, preferred-register: '' }
  - { id: 56, class: anyregbank, preferred-register: '' }
  - { id: 57, class: anyregcls, preferred-register: '' }
  - { id: 58, class: anyregbank, preferred-register: '' }
  - { id: 59, class: anyregcls, preferred-register: '' }
  - { id: 60, class: anyregbank, preferred-register: '' }
  - { id: 61, class: anyregcls, preferred-register: '' }
  - { id: 62, class: anyregbank, preferred-register: '' }
  - { id: 63, class: anyregcls, preferred-register: '' }
  - { id: 64, class: anyregbank, preferred-register: '' }
  - { id: 65, class: anyregcls, preferred-register: '' }
  - { id: 66, class: anyregbank, preferred-register: '' }
  - { id: 67, class: anyregcls, preferred-register: '' }
  - { id: 68, class: anyregbank, preferred-register: '' }
  - { id: 69, class: anyregcls, preferred-register: '' }
  - { id: 70, class: anyregbank, preferred-register: '' }
  - { id: 71, class: anyregcls, preferred-register: '' }
  - { id: 72, class: anyregbank, preferred-register: '' }
  - { id: 73, class: anyregcls, preferred-register: '' }
  - { id: 74, class: anyregcls, preferred-register: '' }
  - { id: 75, class: anyregbank, preferred-register: '' }
  - { id: 76, class: anyregcls, preferred-register: '' }
  - { id: 77, class: anyregbank, preferred-register: '' }
  - { id: 78, class: anyregcls, preferred-register: '' }
  - { id: 79, class: anyregbank, preferred-register: '' }
  - { id: 80, class: anyregcls, preferred-register: '' }
  - { id: 81, class: anyregcls, preferred-register: '' }
  - { id: 82, class: anyregcls, preferred-register: '' }
  - { id: 83, class: anyregcls, preferred-register: '' }
  - { id: 84, class: anyregcls, preferred-register: '' }
  - { id: 85, class: anyregcls, preferred-register: '' }
  - { id: 86, class: anyregcls, preferred-register: '' }
  - { id: 87, class: anyregcls, preferred-register: '' }
  - { id: 88, class: anyregcls, preferred-register: '' }
  - { id: 89, class: anyregcls, preferred-register: '' }
  - { id: 90, class: anyregcls, preferred-register: '' }
  - { id: 91, class: anyregcls, preferred-register: '' }
  - { id: 92, class: anyregcls, preferred-register: '' }
  - { id: 93, class: anyregcls, preferred-register: '' }
  - { id: 94, class: anyregcls, preferred-register: '' }
  - { id: 95, class: anyregcls, preferred-register: '' }
  - { id: 96, class: anyregcls, preferred-register: '' }
  - { id: 97, class: anyregcls, preferred-register: '' }
  - { id: 98, class: anyregcls, preferred-register: '' }
  - { id: 99, class: anyregcls, preferred-register: '' }
  - { id: 100, class: anyregcls, preferred-register: '' }
  - { id: 101, class: anyregcls, preferred-register: '' }
  - { id: 102, class: anyregcls, preferred-register: '' }
  - { id: 103, class: anyregcls, preferred-register: '' }
  - { id: 104, class: anyregcls, preferred-register: '' }
  - { id: 105, class: anyregcls, preferred-register: '' }
  - { id: 106, class: anyregcls, preferred-register: '' }
  - { id: 107, class: anyregcls, preferred-register: '' }
  - { id: 108, class: anyregcls, preferred-register: '' }
  - { id: 109, class: anyregcls, preferred-register: '' }
  - { id: 110, class: anyregcls, preferred-register: '' }
  - { id: 111, class: anyregcls, preferred-register: '' }
  - { id: 112, class: anyregcls, preferred-register: '' }
  - { id: 113, class: anyregcls, preferred-register: '' }
  - { id: 114, class: anyregcls, preferred-register: '' }
  - { id: 115, class: anyregcls, preferred-register: '' }
  - { id: 116, class: anyregcls, preferred-register: '' }
  - { id: 117, class: anyregcls, preferred-register: '' }
  - { id: 118, class: anyregcls, preferred-register: '' }
  - { id: 119, class: anyregcls, preferred-register: '' }
  - { id: 120, class: anyregcls, preferred-register: '' }
  - { id: 121, class: anyregcls, preferred-register: '' }
  - { id: 122, class: anyregcls, preferred-register: '' }
  - { id: 123, class: anyregcls, preferred-register: '' }
  - { id: 124, class: anyregcls, preferred-register: '' }
  - { id: 125, class: anyregcls, preferred-register: '' }
  - { id: 126, class: anyregcls, preferred-register: '' }
  - { id: 127, class: _, preferred-register: '' }
  - { id: 128, class: _, preferred-register: '' }
  - { id: 129, class: anyregcls, preferred-register: '' }
  - { id: 130, class: anyregcls, preferred-register: '' }
liveins:         []
frameInfo:
  isFrameAddressTaken: false
  isReturnAddressTaken: false
  hasStackMap:     false
  hasPatchPoint:   false
  stackSize:       0
  offsetAdjustment: 0
  maxAlignment:    1
  adjustsStack:    false
  hasCalls:        false
  stackProtector:  ''
  functionContext: ''
  maxCallFrameSize: 4294967295
  cvBytesOfCalleeSavedRegisters: 0
  hasOpaqueSPAdjustment: false
  hasVAStart:      false
  hasMustTailInVarArgFunc: false
  hasTailCall:     false
  localFrameSize:  0
  savePoint:       ''
  restorePoint:    ''
fixedStack:      []
stack:           []
entry_values:    []
callSites:       []
debugValueSubstitutions: []
constants:       []
machineFunctionInfo: {}
body:             |
  bb.0.test_mergeRegSet:
    successors: %bb.1(0x80000000)
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.blockL42i0_42:
    successors: %bb.2(0x30000000), %bb.3(0x50000000)
  
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 16, 1 :: (volatile load (s16) from %ir.a, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %2(s16), i16 0
    %129:anyregcls(s16) = HWTFPGA_MUX i16 0
    %130:anyregcls(s12) = HWTFPGA_MUX i12 0
    HWTFPGA_BRCOND %4(s1), %bb.3
  
  bb.2.blockL42i0_42_afterCall:
    successors: %bb.1(0x80000000)
  
    %125:anyregcls(s64) = HWTFPGA_MERGE_VALUES %129(s16), i36 0, %130(s12), 16, 36, 12
    HWTFPGA_CSTORE %125(s64), %1, 0, 64, 1 :: (volatile store (s64) into %ir.res, align 4, addrspace 2)
    HWTFPGA_BR %bb.1
  
  bb.3.blockL42i0__IEEE754FpFromInt_152__416:
    successors: %bb.2(0x80000000)
  
    %5:anyregcls(s1) = HWTFPGA_EXTRACT %2(s16), 15, 1
    %7:anyregcls(s16) = HWTFPGA_SUB i16 0, %2(s16)
    %8:anyregcls(s16) = HWTFPGA_MUX %7(s16), %5(s1), %2(s16)
    %9:anyregcls(s1) = HWTFPGA_EXTRACT %8(s16), 0, 1
    %11:anyregcls(s2) = HWTFPGA_EXTRACT %8(s16), 0, 2
    %12:anyregcls(s3) = HWTFPGA_EXTRACT %8(s16), 0, 3
    %13:anyregcls(s4) = HWTFPGA_EXTRACT %8(s16), 0, 4
    %14:anyregcls(s5) = HWTFPGA_EXTRACT %8(s16), 0, 5
    %15:anyregcls(s6) = HWTFPGA_EXTRACT %8(s16), 0, 6
    %16:anyregcls(s7) = HWTFPGA_EXTRACT %8(s16), 0, 7
    %17:anyregcls(s8) = HWTFPGA_EXTRACT %8(s16), 0, 8
    %18:anyregcls(s9) = HWTFPGA_EXTRACT %8(s16), 0, 9
    %19:anyregcls(s10) = HWTFPGA_EXTRACT %8(s16), 0, 10
    %20:anyregcls(s11) = HWTFPGA_EXTRACT %8(s16), 0, 11
    %21:anyregcls(s12) = HWTFPGA_EXTRACT %8(s16), 0, 12
    %22:anyregcls(s13) = HWTFPGA_EXTRACT %8(s16), 0, 13
    %23:anyregcls(s14) = HWTFPGA_EXTRACT %8(s16), 0, 14
    %24:anyregcls(s15) = HWTFPGA_EXTRACT %8(s16), 0, 15
    %25:anyregcls(s8) = HWTFPGA_EXTRACT %8(s16), 8, 8
    %28:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %25(s8), i8 0
    %29:anyregcls(s8) = HWTFPGA_MUX %17(s8), %28(s1), %25(s8)
    %30:anyregcls(s4) = HWTFPGA_EXTRACT %29(s8), 4, 4
    %33:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %30(s4), i4 0
    %34:anyregcls(s4) = HWTFPGA_EXTRACT %29(s8), 0, 4
    %35:anyregcls(s4) = HWTFPGA_MUX %34(s4), %33(s1), %30(s4)
    %36:anyregcls(s2) = HWTFPGA_EXTRACT %35(s4), 2, 2
    %39:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %36(s2), i2 0
    %40:anyregcls(s2) = HWTFPGA_EXTRACT %35(s4), 0, 2
    %42:anyregcls(s2) = HWTFPGA_MUX %40(s2), %39(s1), %36(s2)
    %43:anyregcls(s1) = HWTFPGA_EXTRACT %42(s2), 1, 1
    %46:anyregcls(s1) = HWTFPGA_NOT %43(s1)
    %47:anyregcls(s11) = HWTFPGA_MERGE_VALUES %46(s1), %39(s1), %33(s1), %28(s1), i7 0, 1, 1, 1, 1, 7
    %50:anyregcls(s11) = HWTFPGA_SUB i11 -1010, %47(s11)
    %51:anyregcls(s4) = HWTFPGA_MERGE_VALUES %46(s1), %39(s1), %33(s1), %28(s1), 1, 1, 1, 1
    %53:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -1
    %55:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -2
    %57:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -3
    %59:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -4
    %61:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -5
    %63:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -6
    %65:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -7
    %67:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 -8
    %69:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 7
    %71:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 6
    %73:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 5
    %74:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 4
    %76:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 3
    %78:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 2
    %80:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 1
    %81:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %51(s4), i4 0
    %83:anyregcls(s16) = HWTFPGA_MERGE_VALUES i1 false, %24(s15), 1, 15
    %86:anyregcls(s16) = HWTFPGA_MERGE_VALUES i2 0, %23(s14), 2, 14
    %88:anyregcls(s16) = HWTFPGA_MERGE_VALUES i3 0, %22(s13), 3, 13
    %90:anyregcls(s16) = HWTFPGA_MERGE_VALUES i4 0, %21(s12), 4, 12
    %92:anyregcls(s16) = HWTFPGA_MERGE_VALUES i5 0, %20(s11), 5, 11
    %94:anyregcls(s16) = HWTFPGA_MERGE_VALUES i6 0, %19(s10), 6, 10
    %97:anyregcls(s16) = HWTFPGA_MERGE_VALUES i7 0, %18(s9), 7, 9
    %99:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, %17(s8), 8, 8
    %101:anyregcls(s16) = HWTFPGA_MERGE_VALUES i9 0, %16(s7), 9, 7
    %104:anyregcls(s16) = HWTFPGA_MERGE_VALUES i10 0, %15(s6), 10, 6
    %107:anyregcls(s16) = HWTFPGA_MERGE_VALUES i11 0, %14(s5), 11, 5
    %110:anyregcls(s16) = HWTFPGA_MERGE_VALUES i12 0, %13(s4), 12, 4
    %113:anyregcls(s16) = HWTFPGA_MERGE_VALUES i13 0, %12(s3), 13, 3
    %116:anyregcls(s16) = HWTFPGA_MERGE_VALUES i14 0, %11(s2), 14, 2
    %119:anyregcls(s16) = HWTFPGA_MERGE_VALUES i15 0, %9(s1), 15, 1
    %129:anyregcls(s16) = HWTFPGA_MUX %119(s16), %53(s1), %116(s16), %55(s1), %113(s16), %57(s1), %110(s16), %59(s1), %107(s16), %61(s1), %104(s16), %63(s1), %101(s16), %65(s1), %99(s16), %67(s1), %97(s16), %69(s1), %94(s16), %71(s1), %92(s16), %73(s1), %90(s16), %74(s1), %88(s16), %76(s1), %86(s16), %78(s1), %83(s16), %80(s1), %8(s16), %81(s1), i16 0
    %130:anyregcls(s12) = HWTFPGA_MERGE_VALUES %50(s11), %5(s1), 11, 1
    HWTFPGA_BR %bb.2

...
