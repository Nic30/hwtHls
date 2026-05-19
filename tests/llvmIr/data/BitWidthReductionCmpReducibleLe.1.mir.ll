--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @"BitWidthReductionCmpReducibleEq.hwImpl.<locals>.mainThread"(ptr addrspace(1) %a, ptr addrspace(2) %b, ptr addrspace(3) %res, ptr addrspace(4) %res_prefix_0vs1, ptr addrspace(5) %res_prefix_0vsAll, ptr addrspace(6) %res_prefix_aVs0, ptr addrspace(7) %res_prefix_aVsAll, ptr addrspace(8) %res_prefix_bVs0, ptr addrspace(9) %res_prefix_bVsAll, ptr addrspace(10) %res_prefix_differentInMiddle, ptr addrspace(11) %res_prefix_same, ptr addrspace(12) %res_prefix_sameInMiddle, ptr addrspace(13) %res_prefix_same_1, ptr addrspace(14) %res_same, ptr addrspace(15) %res_suffix_0vsB, ptr addrspace(16) %res_suffix_AllVsB, ptr addrspace(17) %res_suffix_aVs0, ptr addrspace(18) %res_suffix_aVsAll) !hwtHls.io !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %bb0, %loopHeader
    %a_read2 = load volatile i8, ptr addrspace(1) %a, align 1
    %0 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %a_read2, i4 0) #1
    %1 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %a_read2, i4 4) #1
    %b_read2 = load volatile i8, ptr addrspace(2) %b, align 1
    %2 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8 %b_read2, i4 0) #1
    %3 = call i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8 %b_read2, i4 4) #1
    %4 = icmp ule i8 %a_read2, %b_read2
    store volatile i1 %4, ptr addrspace(3) %res, align 1
    store volatile i1 true, ptr addrspace(14) %res_same, align 1
    store volatile i1 %4, ptr addrspace(11) %res_prefix_same, align 1
    store volatile i1 %4, ptr addrspace(13) %res_prefix_same_1, align 1
    %5 = call i9 @hwtHls.bitConcat.i8.i1(i8 %b_read2, i1 true) #1
    %6 = zext i8 %a_read2 to i9
    %7 = icmp uge i9 %5, %6
    store volatile i1 %7, ptr addrspace(4) %res_prefix_0vs1, align 1
    %8 = call i13 @hwtHls.bitConcat.i8.i5(i8 %b_read2, i5 -1) #1
    %9 = zext i8 %a_read2 to i13
    %10 = icmp uge i13 %8, %9
    store volatile i1 %10, ptr addrspace(5) %res_prefix_0vsAll, align 1
    %11 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read2, i8 %a_read2) #1
    %12 = zext i8 %b_read2 to i16
    %13 = icmp ule i16 %11, %12
    store volatile i1 %13, ptr addrspace(17) %res_suffix_aVs0, align 1
    %14 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read2, i8 -1) #1
    %15 = icmp ule i16 %11, %14
    store volatile i1 %15, ptr addrspace(18) %res_suffix_aVsAll, align 1
    %16 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read2, i8 %b_read2) #1
    %17 = zext i8 %a_read2 to i16
    %18 = icmp uge i16 %16, %17
    store volatile i1 %18, ptr addrspace(15) %res_suffix_0vsB, align 1
    %19 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read2, i8 -1) #1
    %20 = icmp ule i16 %19, %16
    store volatile i1 %20, ptr addrspace(16) %res_suffix_AllVsB, align 1
    %21 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %b_read2) #1
    %22 = icmp ule i16 %11, %21
    store volatile i1 %22, ptr addrspace(6) %res_prefix_aVs0, align 1
    %23 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %b_read2) #1
    %24 = icmp ule i16 %11, %23
    store volatile i1 %24, ptr addrspace(7) %res_prefix_aVsAll, align 1
    %25 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %a_read2) #1
    %26 = icmp ule i16 %25, %16
    store volatile i1 %26, ptr addrspace(8) %res_prefix_bVs0, align 1
    %27 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %a_read2) #1
    %28 = icmp ule i16 %27, %16
    store volatile i1 %28, ptr addrspace(9) %res_prefix_bVsAll, align 1
    store volatile i1 %4, ptr addrspace(12) %res_prefix_sameInMiddle, align 1
    %29 = call i13 @hwtHls.bitConcat.i4.i5.i4(i4 %0, i5 0, i4 %1) #1
    %30 = call i13 @hwtHls.bitConcat.i4.i5.i4(i4 %2, i5 -1, i4 %3) #1
    %31 = icmp ule i13 %29, %30
    store volatile i1 %31, ptr addrspace(10) %res_prefix_differentInMiddle, align 1
    br label %loopHeader
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitRangeGet.i8.i4.i4.4(i8, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitRangeGet.i8.i4.i4.0(i8, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i9 @hwtHls.bitConcat.i8.i1(i8, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i13 @hwtHls.bitConcat.i8.i5(i8, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i13 @hwtHls.bitConcat.i4.i5.i4(i4, i5, i4) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2, !3, !4, !5, !6, !7, !8, !9, !10, !11, !12, !13, !14, !15, !16, !17, !18}
  !1 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 0}
  !2 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 1}
  !3 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 2}
  !4 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 3}
  !5 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 4}
  !6 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 5}
  !7 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 6}
  !8 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 7}
  !9 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 8}
  !10 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 9}
  !11 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 10}
  !12 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 11}
  !13 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 12}
  !14 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 13}
  !15 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 14}
  !16 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 15}
  !17 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 16}
  !18 = !{!"OUT", i64 0, i64 0, i64 1, ptr null, i64 17}
...
---
name:            'BitWidthReductionCmpReducibleEq.hwImpl.<locals>.mainThread'
alignment:       1
exposesReturnsTwice: false
legalized:       true
regBankSelected: true
selected:        true
failedISel:      false
tracksRegLiveness: true
hasWinCFI:       false
noPhis:          true
isSSA:           false
noVRegs:         false
hasFakeUses:     false
callsEHReturn:   false
callsUnwindInit: false
hasEHContTarget: false
hasEHScopes:     false
hasEHFunclets:   false
isOutlined:      false
debugInstrRef:   false
failsVerification: false
tracksDebugUserValues: false
registers:
  - { id: 0, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 1, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 2, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 3, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 4, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 7, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 11, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 13, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 14, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 15, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 16, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 17, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 18, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 19, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 20, class: _, preferred-register: '', flags: [  ] }
  - { id: 21, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 22, class: _, preferred-register: '', flags: [  ] }
  - { id: 23, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 24, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 25, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 26, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 27, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 28, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 29, class: _, preferred-register: '', flags: [  ] }
  - { id: 30, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 31, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 32, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 33, class: _, preferred-register: '', flags: [  ] }
  - { id: 34, class: _, preferred-register: '', flags: [  ] }
  - { id: 35, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 36, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 37, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 38, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 39, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 40, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 41, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 42, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 43, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 44, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 45, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 46, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 47, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 48, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 49, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 50, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 51, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 52, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 53, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 54, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 55, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 56, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 57, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 58, class: anyregcls, preferred-register: '', flags: [  ] }
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
  isCalleeSavedInfoValid: false
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
    %2:anyregcls = HWTFPGA_ARG_GET 2
    %3:anyregcls = HWTFPGA_ARG_GET 3
    %4:anyregcls = HWTFPGA_ARG_GET 4
    %5:anyregcls = HWTFPGA_ARG_GET 5
    %6:anyregcls = HWTFPGA_ARG_GET 6
    %7:anyregcls = HWTFPGA_ARG_GET 7
    %8:anyregcls = HWTFPGA_ARG_GET 8
    %9:anyregcls = HWTFPGA_ARG_GET 9
    %10:anyregcls = HWTFPGA_ARG_GET 10
    %11:anyregcls = HWTFPGA_ARG_GET 11
    %12:anyregcls = HWTFPGA_ARG_GET 12
    %13:anyregcls = HWTFPGA_ARG_GET 13
    %14:anyregcls = HWTFPGA_ARG_GET 14
    %15:anyregcls = HWTFPGA_ARG_GET 15
    %16:anyregcls = HWTFPGA_ARG_GET 16
    %17:anyregcls = HWTFPGA_ARG_GET 17
  
  bb.1.loopHeader:
    successors: %bb.1(0x80000000)
  
    %18:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.a, addrspace 1)
    %19:anyregcls(s4) = HWTFPGA_EXTRACT %18(s8), 8, 0, 4
    %21:anyregcls(s4) = HWTFPGA_EXTRACT %18(s8), 8, 4, 4
    %23:anyregcls(s8) = HWTFPGA_CLOAD %1, 0, 8, 1 :: (volatile load (s8) from %ir.b, addrspace 2)
    %24:anyregcls(s4) = HWTFPGA_EXTRACT %23(s8), 8, 0, 4
    %25:anyregcls(s4) = HWTFPGA_EXTRACT %23(s8), 8, 4, 4
    %26:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %18(s8), %23
    HWTFPGA_CSTORE %26(s1), %2, 0, 1, 1 :: (volatile store (s1) into %ir.res, addrspace 3)
    HWTFPGA_CSTORE i1 true, %13, 0, 1, 1 :: (volatile store (s1) into %ir.res_same, addrspace 14)
    HWTFPGA_CSTORE %26(s1), %10, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_same, addrspace 11)
    HWTFPGA_CSTORE %26(s1), %12, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_same_1, addrspace 13)
    HWTFPGA_CSTORE i1 true, %3, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_0vs1, addrspace 4)
    HWTFPGA_CSTORE i1 true, %4, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_0vsAll, addrspace 5)
    %35:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), %18(s8), 8, 8
    %36:anyregcls(s16) = HWTFPGA_MERGE_VALUES %23(s8), i8 0, 8, 8
    %37:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %35(s16), %36
    HWTFPGA_CSTORE %37(s1), %16, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_aVs0, addrspace 17)
    %38:anyregcls(s16) = HWTFPGA_MERGE_VALUES %23(s8), i8 -1, 8, 8
    %40:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %35(s16), %38
    HWTFPGA_CSTORE %40(s1), %17, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_aVsAll, addrspace 18)
    %41:anyregcls(s16) = HWTFPGA_MERGE_VALUES %23(s8), %23(s8), 8, 8
    %42:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), i8 0, 8, 8
    %43:anyregcls(s1) = HWTFPGA_ICMP intpred(uge), %41(s16), %42
    HWTFPGA_CSTORE %43(s1), %14, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_0vsB, addrspace 15)
    %44:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), i8 -1, 8, 8
    %45:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %44(s16), %41
    HWTFPGA_CSTORE %45(s1), %15, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_AllVsB, addrspace 16)
    %46:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, %23(s8), 8, 8
    %48:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %35(s16), %46
    HWTFPGA_CSTORE %48(s1), %5, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_aVs0, addrspace 6)
    %49:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 -1, %23(s8), 8, 8
    %50:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %35(s16), %49
    HWTFPGA_CSTORE %50(s1), %6, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_aVsAll, addrspace 7)
    %51:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, %18(s8), 8, 8
    %52:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %51(s16), %41
    HWTFPGA_CSTORE %52(s1), %7, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_bVs0, addrspace 8)
    %53:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 -1, %18(s8), 8, 8
    %54:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %53(s16), %41
    HWTFPGA_CSTORE %54(s1), %8, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_bVsAll, addrspace 9)
    HWTFPGA_CSTORE %26(s1), %11, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_sameInMiddle, addrspace 12)
    %55:anyregcls(s13) = HWTFPGA_MERGE_VALUES %19(s4), i5 0, %21(s4), 4, 5, 4
    %57:anyregcls(s13) = HWTFPGA_MERGE_VALUES %24(s4), i5 -1, %25(s4), 4, 5, 4
    %58:anyregcls(s1) = HWTFPGA_ICMP intpred(ule), %55(s13), %57
    HWTFPGA_CSTORE %58(s1), %9, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_differentInMiddle, addrspace 10)
    HWTFPGA_BR %bb.1
...
