--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i8.i8(i8, i8) #0
  
  define void @"BitWidthReductionCmpReducibleEq.hwImpl.<locals>.mainThread"(ptr addrspace(1) %a, ptr addrspace(2) %b, ptr addrspace(3) %res, ptr addrspace(4) %res_prefix_0vs1, ptr addrspace(5) %res_prefix_0vsAll, ptr addrspace(6) %res_prefix_aVs0, ptr addrspace(7) %res_prefix_aVsAll, ptr addrspace(8) %res_prefix_bVs0, ptr addrspace(9) %res_prefix_bVsAll, ptr addrspace(10) %res_prefix_differentInMiddle, ptr addrspace(11) %res_prefix_same, ptr addrspace(12) %res_prefix_sameInMiddle, ptr addrspace(13) %res_prefix_same_1, ptr addrspace(14) %res_same, ptr addrspace(15) %res_suffix_0vsB, ptr addrspace(16) %res_suffix_AllVsB, ptr addrspace(17) %res_suffix_aVs0, ptr addrspace(18) %res_suffix_aVsAll) !hwtHls.io !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %bb0, %loopHeader
    %a_read2 = load volatile i8, ptr addrspace(1) %a, align 1
    %b_read2 = load volatile i8, ptr addrspace(2) %b, align 1
    %0 = icmp ne i8 %a_read2, %b_read2
    store volatile i1 %0, ptr addrspace(3) %res, align 1
    store volatile i1 false, ptr addrspace(14) %res_same, align 1
    store volatile i1 %0, ptr addrspace(11) %res_prefix_same, align 1
    store volatile i1 %0, ptr addrspace(13) %res_prefix_same_1, align 1
    store volatile i1 true, ptr addrspace(4) %res_prefix_0vs1, align 1
    store volatile i1 true, ptr addrspace(5) %res_prefix_0vsAll, align 1
    %1 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read2, i8 %a_read2) #1
    %2 = zext i8 %b_read2 to i16
    %3 = icmp ne i16 %1, %2
    store volatile i1 %3, ptr addrspace(17) %res_suffix_aVs0, align 1
    %4 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read2, i8 -1) #1
    %5 = icmp ne i16 %1, %4
    store volatile i1 %5, ptr addrspace(18) %res_suffix_aVsAll, align 1
    %6 = call i16 @hwtHls.bitConcat.i8.i8(i8 %b_read2, i8 %b_read2) #1
    %7 = zext i8 %a_read2 to i16
    %8 = icmp ne i16 %6, %7
    store volatile i1 %8, ptr addrspace(15) %res_suffix_0vsB, align 1
    %9 = call i16 @hwtHls.bitConcat.i8.i8(i8 %a_read2, i8 -1) #1
    %10 = icmp ne i16 %9, %6
    store volatile i1 %10, ptr addrspace(16) %res_suffix_AllVsB, align 1
    %11 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %b_read2) #1
    %12 = icmp ne i16 %1, %11
    store volatile i1 %12, ptr addrspace(6) %res_prefix_aVs0, align 1
    %13 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %b_read2) #1
    %14 = icmp ne i16 %1, %13
    store volatile i1 %14, ptr addrspace(7) %res_prefix_aVsAll, align 1
    %15 = call i16 @hwtHls.bitConcat.i8.i8(i8 0, i8 %a_read2) #1
    %16 = icmp ne i16 %15, %6
    store volatile i1 %16, ptr addrspace(8) %res_prefix_bVs0, align 1
    %17 = call i16 @hwtHls.bitConcat.i8.i8(i8 -1, i8 %a_read2) #1
    %18 = icmp ne i16 %17, %6
    store volatile i1 %18, ptr addrspace(9) %res_prefix_bVsAll, align 1
    store volatile i1 %0, ptr addrspace(12) %res_prefix_sameInMiddle, align 1
    store volatile i1 true, ptr addrspace(10) %res_prefix_differentInMiddle, align 1
    br label %loopHeader
  }
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2, !3, !4, !5, !6, !7, !8, !9, !10, !11, !12, !13, !14, !15, !16, !17, !18, !19}
  !2 = !{!"IN", i64 0, ptr null, i64 0}
  !3 = !{!"IN", i64 0, ptr null, i64 1}
  !4 = !{!"OUT", i64 0, ptr null, i64 2}
  !5 = !{!"OUT", i64 0, ptr null, i64 3}
  !6 = !{!"OUT", i64 0, ptr null, i64 4}
  !7 = !{!"OUT", i64 0, ptr null, i64 5}
  !8 = !{!"OUT", i64 0, ptr null, i64 6}
  !9 = !{!"OUT", i64 0, ptr null, i64 7}
  !10 = !{!"OUT", i64 0, ptr null, i64 8}
  !11 = !{!"OUT", i64 0, ptr null, i64 9}
  !12 = !{!"OUT", i64 0, ptr null, i64 10}
  !13 = !{!"OUT", i64 0, ptr null, i64 11}
  !14 = !{!"OUT", i64 0, ptr null, i64 12}
  !15 = !{!"OUT", i64 0, ptr null, i64 13}
  !16 = !{!"OUT", i64 0, ptr null, i64 14}
  !17 = !{!"OUT", i64 0, ptr null, i64 15}
  !18 = !{!"OUT", i64 0, ptr null, i64 16}
  !19 = !{!"OUT", i64 0, ptr null, i64 17}

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
  - { id: 21, class: anyregbank, preferred-register: '' }
  - { id: 22, class: anyregbank, preferred-register: '' }
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
    %19:anyregcls(s8) = HWTFPGA_CLOAD %1, 0, 8, 1 :: (volatile load (s8) from %ir.b, addrspace 2)
    %20:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %18(s8), %19
    HWTFPGA_CSTORE %20(s1), %2, 0, 1, 1 :: (volatile store (s1) into %ir.res, addrspace 3)
    HWTFPGA_CSTORE i1 false, %13, 0, 1, 1 :: (volatile store (s1) into %ir.res_same, addrspace 14)
    HWTFPGA_CSTORE %20(s1), %10, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_same, addrspace 11)
    HWTFPGA_CSTORE %20(s1), %12, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_same_1, addrspace 13)
    HWTFPGA_CSTORE i1 true, %3, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_0vs1, addrspace 4)
    HWTFPGA_CSTORE i1 true, %4, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_0vsAll, addrspace 5)
    %23:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), %18(s8), 8, 8
    %24:anyregcls(s16) = HWTFPGA_MERGE_VALUES %19(s8), i8 0, 8, 8
    %25:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %23(s16), %24
    HWTFPGA_CSTORE %25(s1), %16, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_aVs0, addrspace 17)
    %26:anyregcls(s16) = HWTFPGA_MERGE_VALUES %19(s8), i8 -1, 8, 8
    %28:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %23(s16), %26
    HWTFPGA_CSTORE %28(s1), %17, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_aVsAll, addrspace 18)
    %29:anyregcls(s16) = HWTFPGA_MERGE_VALUES %19(s8), %19(s8), 8, 8
    %30:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), i8 0, 8, 8
    %31:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %29(s16), %30
    HWTFPGA_CSTORE %31(s1), %14, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_0vsB, addrspace 15)
    %32:anyregcls(s16) = HWTFPGA_MERGE_VALUES %18(s8), i8 -1, 8, 8
    %33:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %32(s16), %29
    HWTFPGA_CSTORE %33(s1), %15, 0, 1, 1 :: (volatile store (s1) into %ir.res_suffix_AllVsB, addrspace 16)
    %34:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, %19(s8), 8, 8
    %36:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %23(s16), %34
    HWTFPGA_CSTORE %36(s1), %5, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_aVs0, addrspace 6)
    %37:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 -1, %19(s8), 8, 8
    %38:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %23(s16), %37
    HWTFPGA_CSTORE %38(s1), %6, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_aVsAll, addrspace 7)
    %39:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 0, %18(s8), 8, 8
    %40:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %39(s16), %29
    HWTFPGA_CSTORE %40(s1), %7, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_bVs0, addrspace 8)
    %41:anyregcls(s16) = HWTFPGA_MERGE_VALUES i8 -1, %18(s8), 8, 8
    %42:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %41(s16), %29
    HWTFPGA_CSTORE %42(s1), %8, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_bVsAll, addrspace 9)
    HWTFPGA_CSTORE %20(s1), %11, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_sameInMiddle, addrspace 12)
    HWTFPGA_CSTORE i1 true, %9, 0, 1, 1 :: (volatile store (s1) into %ir.res_prefix_differentInMiddle, addrspace 10)
    HWTFPGA_BR %bb.1

...
