--- |
  ; ModuleID = 'EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop'
  source_filename = "EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop(ptr addrspace(1) %bodyTx, ptr addrspace(2) %rx) !hwtHls.param_addr_width !0 {
  EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop:
    br label %blockL44i0_44
  
  blockL44i0_44:                                    ; preds = %blockL44i0_656, %blockL44i0_L738i0_738, %EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop
    %rx14 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx15 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx16 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx17 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx18 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx19 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx20 = load volatile i19, ptr addrspace(2) %rx, align 4
    %0 = call i16 @hwtHls.bitRangeGet.i19.i64.i16.0(i19 %rx20, i64 0) #1
    %"313" = icmp eq i16 %0, 2048
    br i1 %"313", label %blockL44i0_244, label %blockL44i0_L738i0_738.preheader
  
  blockL44i0_L738i0_738.preheader:                  ; preds = %blockL44i0_44
    br label %blockL44i0_L738i0_738
  
  blockL44i0_244:                                   ; preds = %blockL44i0_44
    %rx62 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx63 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx64 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx65 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx66 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx67 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx68 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx69 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx70 = load volatile i19, ptr addrspace(2) %rx, align 4
    %rx71 = load volatile i19, ptr addrspace(2) %rx, align 4
    br label %blockL44i0_L376i0_376
  
  blockL44i0_L376i0_376:                            ; preds = %blockL44i0_L376i0_376.1, %blockL44i0_244
    %"%180214" = phi i8 [ 0, %blockL44i0_244 ], [ %6, %blockL44i0_L376i0_376.1 ]
    %"%181915" = phi i1 [ false, %blockL44i0_244 ], [ true, %blockL44i0_L376i0_376.1 ]
    %rx133 = load volatile i19, ptr addrspace(2) %rx, align 4
    %1 = call i1 @hwtHls.bitRangeGet.i19.i64.i1.18(i19 %rx133, i64 18) #1
    %2 = call i19 @hwtHls.bitConcat.i8.i8.i1.i1.i1(i8 0, i8 %"%180214", i1 false, i1 %"%181915", i1 false) #1
    store volatile i19 %2, ptr addrspace(1) %bodyTx, align 4
    br i1 %1, label %blockL44i0_656, label %blockL44i0_L376i0_376.1, !llvm.loop !2
  
  blockL44i0_L376i0_376.1:                          ; preds = %blockL44i0_L376i0_376
    %3 = call i8 @hwtHls.bitRangeGet.i19.i64.i8.8(i19 %rx133, i64 8) #1
    %rx133.1 = load volatile i19, ptr addrspace(2) %rx, align 4
    %4 = call i1 @hwtHls.bitRangeGet.i19.i64.i1.18(i19 %rx133.1, i64 18) #1
    %5 = call i19 @hwtHls.bitConcat.i8.i8.i3(i8 0, i8 %3, i3 2) #1
    store volatile i19 %5, ptr addrspace(1) %bodyTx, align 4
    %6 = call i8 @hwtHls.bitRangeGet.i19.i64.i8.8(i19 %rx133.1, i64 8) #1
    br i1 %4, label %blockL44i0_656, label %blockL44i0_L376i0_376, !llvm.loop !5
  
  blockL44i0_656:                                   ; preds = %blockL44i0_L376i0_376.1, %blockL44i0_L376i0_376
    %rx133.lcssa = phi i19 [ %rx133, %blockL44i0_L376i0_376 ], [ %rx133.1, %blockL44i0_L376i0_376.1 ]
    %7 = call i8 @hwtHls.bitRangeGet.i19.i64.i8.0(i19 %rx133.lcssa, i64 0) #1
    %8 = call i19 @hwtHls.bitConcat.i8.i8.i3(i8 0, i8 %7, i3 -2) #1
    store volatile i19 %8, ptr addrspace(1) %bodyTx, align 4
    br label %blockL44i0_44
  
  blockL44i0_L738i0_738:                            ; preds = %blockL44i0_L738i0_738.preheader, %blockL44i0_L738i0_738
    %rx151 = load volatile i19, ptr addrspace(2) %rx, align 4
    %9 = call i1 @hwtHls.bitRangeGet.i19.i64.i1.18(i19 %rx151, i64 18) #1
    br i1 %9, label %blockL44i0_44, label %blockL44i0_L738i0_738
  }
  
  ; Function Attrs: nofree nounwind willreturn
  declare i16 @hwtHls.bitRangeGet.i19.i6.i16.0(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i2 @hwtHls.bitRangeGet.i19.i6.i2.16(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i32 @hwtHls.bitConcat.i16.i16(i16, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i4 @hwtHls.bitConcat.i2.i2(i2, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i48 @hwtHls.bitConcat.i32.i16(i32, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i6 @hwtHls.bitConcat.i4.i2(i4, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i64 @hwtHls.bitConcat.i48.i16(i48, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitConcat.i6.i2(i6, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i80 @hwtHls.bitConcat.i64.i16(i64, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i10 @hwtHls.bitConcat.i8.i2(i8, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i96 @hwtHls.bitConcat.i80.i16(i80, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i12 @hwtHls.bitConcat.i10.i2(i10, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i112 @hwtHls.bitConcat.i96.i16(i96, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i14 @hwtHls.bitConcat.i12.i2(i12, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i126 @hwtHls.bitConcat.i112.i14(i112, i14) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i127 @hwtHls.bitConcat.i126.i1(i126, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i16 @hwtHls.bitRangeGet.i127.i8.i16.96(i127, i8) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i128 @hwtHls.bitConcat.i112.i16(i112, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i16 @hwtHls.bitConcat.i14.i2(i14, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i144 @hwtHls.bitConcat.i128.i16(i128, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i18 @hwtHls.bitConcat.i16.i2(i16, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i160 @hwtHls.bitConcat.i144.i16(i144, i16) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i20 @hwtHls.bitConcat.i18.i2(i18, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i180 @hwtHls.bitConcat.i160.i20(i160, i20) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i181 @hwtHls.bitConcat.i180.i1(i180, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i19.i6.i8.0(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i19.i6.i1.16(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i9 @hwtHls.bitConcat.i8.i1(i8, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i10 @hwtHls.bitConcat.i9.i1(i9, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i10.i5.i8.0(i10, i5) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i19 @hwtHls.bitConcat.i18.i1(i18, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i10.i5.i1.9(i10, i5) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i2 @hwtHls.bitConcat.i1.i1(i1, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i16.i5.i8.0(i16, i5) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i19.i6.i8.8(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i19.i6.i1.17(i19, i6) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i1 @hwtHls.bitRangeGet.i19.i64.i1.18(i19, i64) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i16 @hwtHls.bitRangeGet.i19.i64.i16.0(i19, i64) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i19.i64.i8.0(i19, i64) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i8 @hwtHls.bitRangeGet.i19.i64.i8.8(i19, i64) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i19 @hwtHls.bitConcat.i8.i8.i1.i1.i1(i8, i8, i1, i1, i1) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i19 @hwtHls.bitConcat.i8.i8.i1.i2(i8, i8, i1, i2) #0
  
  ; Function Attrs: nofree nounwind willreturn
  declare i19 @hwtHls.bitConcat.i8.i8.i3(i8, i8, i3) #0
  
  attributes #0 = { nofree nounwind willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}
  !2 = distinct !{!2, !3, !4}
  !3 = !{!"llvm.loop.unroll.enable"}
  !4 = !{!"llvm.loop.unroll.count", i32 2}
  !5 = distinct !{!5, !6}
  !6 = !{!"llvm.loop.unroll.disable"}

...
---
name:            EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop
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
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: _, preferred-register: '' }
  - { id: 11, class: anyregbank, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: _, preferred-register: '' }
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
  - { id: 26, class: anyregcls, preferred-register: '' }
  - { id: 27, class: anyregcls, preferred-register: '' }
  - { id: 28, class: anyregcls, preferred-register: '' }
  - { id: 29, class: anyregcls, preferred-register: '' }
  - { id: 30, class: anyregcls, preferred-register: '' }
  - { id: 31, class: anyregcls, preferred-register: '' }
  - { id: 32, class: anyregcls, preferred-register: '' }
  - { id: 33, class: anyregcls, preferred-register: '' }
  - { id: 34, class: _, preferred-register: '' }
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
  - { id: 45, class: anyregbank, preferred-register: '' }
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
  bb.0.EarlyIfConverter_TC_test_mergeExitBlockOfParentLoop:
    successors: %bb.1(0x80000000)
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.blockL44i0_44:
    successors: %bb.2(0x40000000), %bb.6(0x40000000)
  
    dead %2:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %3:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %4:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %5:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %6:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %7:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %8:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %9:anyregcls(s16) = HWTFPGA_EXTRACT %8(s19), 0, 16
    %12:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %9(s16), i16 2048
    %56:anyregcls(s1) = HWTFPGA_NOT %12(s1)
    HWTFPGA_BRCOND %56(s1), %bb.6
  
  bb.2.blockL44i0_244:
    successors: %bb.3(0x80000000)
  
    dead %16:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %17:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %18:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %19:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %20:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %21:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %22:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %23:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %24:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    dead %25:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 19, 1 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %47:anyregcls(s8) = HWTFPGA_MUX i8 0
    %48:anyregcls(s1) = HWTFPGA_MUX i1 false
  
  bb.3.blockL44i0_L376i0_376:
    successors: %bb.5(0x04000000), %bb.4(0x7c000000)
  
    %27:anyregcls(s1) = HWTFPGA_MUX %48(s1)
    %26:anyregcls(s8) = HWTFPGA_MUX %47(s8)
    %28:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %29:anyregcls(s1) = HWTFPGA_EXTRACT %28(s19), 18, 1
    %30:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %26(s8), i1 false, %27(s1), i1 false, 8, 8, 1, 1, 1
    HWTFPGA_CSTORE %30(s19), %0, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
    %49:anyregcls(s19) = HWTFPGA_MUX %28(s19)
    HWTFPGA_BRCOND %29(s1), %bb.5
  
  bb.4.blockL44i0_L376i0_376.1:
    successors: %bb.5(0x04000000), %bb.3(0x7c000000)
  
    %33:anyregcls(s8) = HWTFPGA_EXTRACT %28(s19), 8, 8
    %35:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %36:anyregcls(s1) = HWTFPGA_EXTRACT %35(s19), 18, 1
    %37:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %33(s8), i3 2, 8, 8, 3
    HWTFPGA_CSTORE %37(s19), %0, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
    %47:anyregcls(s8) = HWTFPGA_EXTRACT %35(s19), 8, 8
    %48:anyregcls(s1) = HWTFPGA_MUX i1 true
    %49:anyregcls(s19) = HWTFPGA_MUX %35(s19)
    %52:anyregcls(s1) = HWTFPGA_NOT %36(s1)
    HWTFPGA_BRCOND %52(s1), %bb.3
  
  bb.5.blockL44i0_656:
    successors: %bb.1(0x80000000)
  
    %41:anyregcls(s8) = HWTFPGA_EXTRACT %49(s19), 0, 8
    %42:anyregcls(s19) = HWTFPGA_MERGE_VALUES i8 0, %41(s8), i3 -2, 8, 8, 3
    HWTFPGA_CSTORE %42(s19), %0, 0, 19, 1 :: (volatile store (s19) into %ir.bodyTx, align 4, addrspace 1)
    HWTFPGA_BR %bb.1
  
  bb.6.blockL44i0_L738i0_738:
    successors: %bb.1(0x04000000), %bb.6(0x7c000000)
  
    %13:anyregcls(s19) = HWTFPGA_CLOAD %1, 0, 1, 19 :: (volatile load (s19) from %ir.rx, align 4, addrspace 2)
    %14:anyregcls(s1) = HWTFPGA_EXTRACT %13(s19), 18, 1
    %50:anyregcls(s1) = HWTFPGA_NOT %14(s1)
    HWTFPGA_BRCOND %50(s1), %bb.6
    HWTFPGA_BR %bb.1

...
