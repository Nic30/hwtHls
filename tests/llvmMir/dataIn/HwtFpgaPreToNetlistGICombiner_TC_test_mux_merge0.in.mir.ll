--- |
  ; ModuleID = 'HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0'
  source_filename = "HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0(ptr addrspace(1) %rx, ptr addrspace(2) %txBody) !hwtHls.param_addr_width !0 !hwtHls.streamIo !2 {
  bb0:
    br label %bb2
  
  bb2:                                              ; preds = %14, %bb0
    br label %bb3
  
  bb3:                                              ; preds = %14, %bb2
    %txBodyDataOffset.012 = phi i2 [ 0, %bb2 ], [ %txBodyDataOffset.416, %14 ]
    %txBodyDataMask.0 = phi i3 [ 0, %bb2 ], [ %txBodyDataMask.4, %14 ]
    %txBodyData.013 = phi i16 [ undef, %bb2 ], [ %txBodyData.417, %14 ]
    %0 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3 %txBodyDataMask.0, i3 0) #1
    %"rx2(rx_read).w0" = load volatile i10, ptr addrspace(1) %rx, align 2
    %1 = call i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10 %"rx2(rx_read).w0", i5 0) #1
    %.eof18 = call i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10 %"rx2(rx_read).w0", i5 9) #1
    %2 = call i5 @hwtHls.bitConcat.i3.i2(i3 0, i2 %txBodyDataOffset.012) #1
    %3 = call i27 @hwtHls.bitConcat.i16.i8.i2.i1(i16 %txBodyData.013, i8 %1, i2 %0, i1 true) #1
    switch i5 %2, label %12 [
      i5 0, label %txBodyoff0
      i5 8, label %txBodyoff8
      i5 -16, label %.gvnsink.split
    ]
  
  txBodyoff0:                                       ; preds = %bb3
    %4 = call i27 @hwtHls.bitConcat.i8.i16.i3(i8 %1, i16 undef, i3 1) #1
    %5 = call i16 @hwtHls.bitConcat.i8.i8(i8 %1, i8 undef) #1
    br i1 %.eof18, label %.gvnsink.split, label %14
  
  txBodyoff8:                                       ; preds = %bb3
    %6 = call i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16 %txBodyData.013, i5 0) #1
    %7 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %txBodyDataMask.0, i3 0) #1
    %8 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3 %txBodyDataMask.0, i3 2) #1
    %9 = call i27 @hwtHls.bitConcat.i8.i8.i8.i1.i1.i1(i8 %6, i8 %1, i8 undef, i1 %7, i1 true, i1 %8) #1
    %10 = call i16 @hwtHls.bitConcat.i8.i8(i8 %6, i8 %1) #1
    %11 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %7, i1 true, i1 %8) #1
    br i1 %.eof18, label %.gvnsink.split, label %14
  
  12:                                               ; preds = %bb3
    unreachable
  
  .gvnsink.split:                                   ; preds = %bb3, %txBodyoff8, %txBodyoff0
    %.sink14 = phi i27 [ %4, %txBodyoff0 ], [ %9, %txBodyoff8 ], [ %3, %bb3 ]
    %txBodyData.4.ph15 = phi i16 [ %5, %txBodyoff0 ], [ %10, %txBodyoff8 ], [ undef, %bb3 ]
    %13 = call i28 @hwtHls.bitConcat.i27.i1(i27 %.sink14, i1 %.eof18) #1
    store volatile i28 %13, ptr addrspace(2) %txBody, align 4
    br label %14
  
  14:                                               ; preds = %.gvnsink.split, %txBodyoff8, %txBodyoff0
    %txBodyDataOffset.416 = phi i2 [ 1, %txBodyoff0 ], [ -2, %txBodyoff8 ], [ 0, %.gvnsink.split ]
    %txBodyDataMask.4 = phi i3 [ 1, %txBodyoff0 ], [ %11, %txBodyoff8 ], [ 0, %.gvnsink.split ]
    %txBodyData.417 = phi i16 [ %5, %txBodyoff0 ], [ %10, %txBodyoff8 ], [ %txBodyData.4.ph15, %.gvnsink.split ]
    br i1 %.eof18, label %bb2, label %bb3, !hwthls.loop !5
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i5 @hwtHls.bitConcat.i3.i2(i3, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i28 @hwtHls.bitConcat.i27.i1(i27, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i27 @hwtHls.bitConcat.i8.i16.i3(i8, i16, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i3.i3.i1.2(i3, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i27 @hwtHls.bitConcat.i8.i8.i8.i1.i1.i1(i8, i8, i8, i1, i1, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i3.i3.i2.0(i3, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i27 @hwtHls.bitConcat.i16.i8.i2.i1(i16, i8, i2, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i3 @hwtHls.bitConcat.i1.i1.i1(i1, i1, i1) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}
  !2 = !{!3, !4}
  !3 = !{i32 0, i32 8, i32 1}
  !4 = !{i32 1, i32 24, i32 1}
  !5 = distinct !{!5, !6}
  !6 = !{!"hwthls.loop.streamunroll.io", i32 0}

...
---
name:            HwtFpgaPreToNetlistGICombiner_TC_test_mux_merge0
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
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: _, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: _, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregbank, preferred-register: '' }
  - { id: 16, class: anyregcls, preferred-register: '' }
  - { id: 17, class: anyregbank, preferred-register: '' }
  - { id: 18, class: anyregcls, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregcls, preferred-register: '' }
  - { id: 21, class: anyregcls, preferred-register: '' }
  - { id: 22, class: _, preferred-register: '' }
  - { id: 23, class: anyregcls, preferred-register: '' }
  - { id: 24, class: anyregcls, preferred-register: '' }
  - { id: 25, class: anyregcls, preferred-register: '' }
  - { id: 26, class: anyregcls, preferred-register: '' }
  - { id: 27, class: anyregcls, preferred-register: '' }
  - { id: 28, class: anyregcls, preferred-register: '' }
  - { id: 29, class: anyregcls, preferred-register: '' }
  - { id: 30, class: anyregcls, preferred-register: '' }
  - { id: 31, class: anyregcls, preferred-register: '' }
  - { id: 32, class: anyregcls, preferred-register: '' }
  - { id: 33, class: anyregcls, preferred-register: '' }
  - { id: 34, class: anyregcls, preferred-register: '' }
  - { id: 35, class: anyregcls, preferred-register: '' }
  - { id: 36, class: anyregcls, preferred-register: '' }
  - { id: 37, class: anyregcls, preferred-register: '' }
  - { id: 38, class: anyregcls, preferred-register: '' }
  - { id: 39, class: anyregcls, preferred-register: '' }
  - { id: 40, class: anyregcls, preferred-register: '' }
  - { id: 41, class: anyregcls, preferred-register: '' }
  - { id: 42, class: anyregcls, preferred-register: '' }
  - { id: 43, class: anyregcls, preferred-register: '' }
  - { id: 44, class: anyregcls, preferred-register: '' }
  - { id: 45, class: anyregcls, preferred-register: '' }
  - { id: 46, class: anyregcls, preferred-register: '' }
  - { id: 47, class: anyregcls, preferred-register: '' }
  - { id: 48, class: anyregcls, preferred-register: '' }
  - { id: 49, class: anyregcls, preferred-register: '' }
  - { id: 50, class: anyregcls, preferred-register: '' }
  - { id: 51, class: anyregcls, preferred-register: '' }
  - { id: 52, class: anyregcls, preferred-register: '' }
  - { id: 53, class: anyregcls, preferred-register: '' }
  - { id: 54, class: anyregcls, preferred-register: '' }
  - { id: 55, class: anyregcls, preferred-register: '' }
  - { id: 56, class: anyregcls, preferred-register: '' }
  - { id: 57, class: anyregcls, preferred-register: '' }
  - { id: 58, class: anyregcls, preferred-register: '' }
  - { id: 59, class: anyregcls, preferred-register: '' }
  - { id: 60, class: anyregcls, preferred-register: '' }
  - { id: 61, class: anyregcls, preferred-register: '' }
  - { id: 62, class: anyregcls, preferred-register: '' }
  - { id: 63, class: anyregcls, preferred-register: '' }
  - { id: 64, class: anyregcls, preferred-register: '' }
  - { id: 65, class: anyregcls, preferred-register: '' }
  - { id: 66, class: anyregcls, preferred-register: '' }
  - { id: 67, class: anyregcls, preferred-register: '' }
  - { id: 68, class: anyregcls, preferred-register: '' }
  - { id: 69, class: anyregcls, preferred-register: '' }
  - { id: 70, class: anyregcls, preferred-register: '' }
  - { id: 71, class: anyregcls, preferred-register: '' }
  - { id: 72, class: anyregcls, preferred-register: '' }
  - { id: 73, class: anyregcls, preferred-register: '' }
  - { id: 74, class: anyregcls, preferred-register: '' }
  - { id: 75, class: anyregcls, preferred-register: '' }
  - { id: 76, class: anyregcls, preferred-register: '' }
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
  bb.0.bb0:
    successors: %bb.1(0x80000000)
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.bb2:
    successors: %bb.2(0x80000000)
  
    %42:anyregcls(s2) = HWTFPGA_MUX i2 0
    %43:anyregcls(s3) = HWTFPGA_MUX i3 0
    %44:anyregcls(s16) = IMPLICIT_DEF
  
  bb.2.bb3:
    successors: %bb.1(0x04000000), %bb.2(0x7c000000)
  
    %4:anyregcls(s16) = HWTFPGA_MUX %44(s16)
    %3:anyregcls(s3) = HWTFPGA_MUX %43(s3)
    %5:anyregcls(s2) = HWTFPGA_EXTRACT %3(s3), 0, 2
    %7:anyregcls(s10) = HWTFPGA_CLOAD %0, 0, 1 :: (volatile load (s10) from %ir.rx, addrspace 1)
    %8:anyregcls(s8) = HWTFPGA_EXTRACT %7(s10), 0, 8
    %10:anyregcls(s1) = HWTFPGA_EXTRACT %7(s10), 9, 1
    %12:anyregcls(s5) = HWTFPGA_MERGE_VALUES i3 0, %42(s2), 3, 2
    %16:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s5), i5 -16
    %45:anyregcls(s27) = HWTFPGA_MERGE_VALUES %4(s16), %8(s8), %5(s2), i1 true, 16, 8, 2, 1
    %46:anyregcls(s16) = IMPLICIT_DEF
    %18:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s5), i5 8
    %65:anyregcls(s27) = HWTFPGA_MERGE_VALUES %8(s8), undef %28:anyregcls(s16), i3 1, 8, 16, 3
    %49:anyregcls(s16) = HWTFPGA_MERGE_VALUES %8(s8), undef %24:anyregcls(s8), 8, 8
    %66:anyregcls(s16) = HWTFPGA_MUX %49(s16)
    %47:anyregcls(s2) = HWTFPGA_MUX i2 1
    %48:anyregcls(s3) = HWTFPGA_MUX i3 1
    %19:anyregcls(s8) = HWTFPGA_EXTRACT %4(s16), 0, 8
    %20:anyregcls(s1) = HWTFPGA_EXTRACT %3(s3), 0, 1
    %21:anyregcls(s1) = HWTFPGA_EXTRACT %3(s3), 2, 1
    %60:anyregcls(s27) = HWTFPGA_MERGE_VALUES %19(s8), %8(s8), undef %24:anyregcls(s8), %20(s1), i1 true, %21(s1), 8, 8, 8, 1, 1, 1
    %25:anyregcls(s16) = HWTFPGA_MERGE_VALUES %19(s8), %8(s8), 8, 8
    %61:anyregcls(s3) = HWTFPGA_MERGE_VALUES %20(s1), i1 true, %21(s1), 1, 1, 1
    %65:anyregcls(s27) = HWTFPGA_MUX %60(s27), %18(s1), %65(s27)
    %48:anyregcls(s3) = HWTFPGA_MUX %61(s3), %18(s1), %48(s3)
    %66:anyregcls(s16) = HWTFPGA_MUX %25(s16), %18(s1), %66(s16)
    %47:anyregcls(s2) = HWTFPGA_MUX i2 -2, %18(s1), %47(s2)
    %49:anyregcls(s16) = HWTFPGA_MUX %25(s16), %18(s1), %49(s16)
    %45:anyregcls(s27) = HWTFPGA_MUX %45(s27), %16(s1), %65(s27)
    %46:anyregcls(s16) = HWTFPGA_MUX %46(s16), %16(s1), %66(s16)
    %67:anyregcls(s1) = HWTFPGA_NOT %16(s1)
    %69:anyregcls(s1) = HWTFPGA_NOT %10(s1)
    %71:anyregcls(s1) = HWTFPGA_AND %67(s1), %69(s1)
    %33:anyregcls(s28) = HWTFPGA_MERGE_VALUES %45(s27), %10(s1), 27, 1
    %72:anyregcls(s1) = HWTFPGA_NOT %71(s1)
    HWTFPGA_CSTORE %33(s28), %1, 0, %72(s1) :: (volatile store (s28) into %ir.txBody, addrspace 2)
    %47:anyregcls(s2) = HWTFPGA_MUX %47(s2), %71(s1), i2 0
    %48:anyregcls(s3) = HWTFPGA_MUX %48(s3), %71(s1), i3 0
    %49:anyregcls(s16) = HWTFPGA_MUX %49(s16), %71(s1), %46(s16)
    %42:anyregcls(s2) = HWTFPGA_MUX %47(s2)
    %43:anyregcls(s3) = HWTFPGA_MUX %48(s3)
    %44:anyregcls(s16) = HWTFPGA_MUX %49(s16)
    HWTFPGA_BRCOND %10(s1), %bb.1
    HWTFPGA_BR %bb.2

...
