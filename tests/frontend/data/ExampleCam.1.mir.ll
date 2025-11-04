--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) !hwtHls.io !0 {
  bb0:
    br label %blockL210i0_210
  
  blockL210i0_210:                                  ; preds = %bb0, %blockL210i0_210
    %.phiConc = phi i17 [ 0, %bb0 ], [ %.selConc, %blockL210i0_210 ]
    %.phiConc39 = phi i17 [ 0, %bb0 ], [ %.selConc40, %blockL210i0_210 ]
    %.phiConc41 = phi i17 [ 0, %bb0 ], [ %.selConc42, %blockL210i0_210 ]
    %.phiConc43 = phi i17 [ 0, %bb0 ], [ %.selConc44, %blockL210i0_210 ]
    store volatile i17 %.phiConc, ptr addrspace(1) %keyForMatchThread_0, align 4
    store volatile i17 %.phiConc39, ptr addrspace(2) %keyForMatchThread_1, align 4
    store volatile i17 %.phiConc41, ptr addrspace(3) %keyForMatchThread_2, align 4
    store volatile i17 %.phiConc43, ptr addrspace(4) %keyForMatchThread_3, align 4
    %write_read1 = load volatile i19, ptr addrspace(5) %write, align 4
    %0 = call i17 @hwtHls.bitRangeGet.i19.i6.i17.2(i19 %write_read1, i6 2) #1
    %write_read_addr3 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read1, i6 0) #1
    %1 = icmp eq i2 %write_read_addr3, 0
    %.selConc = select i1 %1, i17 %0, i17 %.phiConc
    %2 = icmp eq i2 %write_read_addr3, 1
    %.selConc40 = select i1 %2, i17 %0, i17 %.phiConc39
    %3 = icmp eq i2 %write_read_addr3, -2
    %.selConc42 = select i1 %3, i17 %0, i17 %.phiConc41
    %4 = icmp eq i2 %write_read_addr3, -1
    %.selConc44 = select i1 %4, i17 %0, i17 %.phiConc43
    br label %blockL210i0_210
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19, i6) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i17 @hwtHls.bitRangeGet.i19.i6.i17.2(i19, i6) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2, !3, !4, !5}
  !1 = !{!"OUT", i64 0, i64 0, i64 17, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 17, ptr null, i64 1}
  !3 = !{!"OUT", i64 0, i64 0, i64 17, ptr null, i64 2}
  !4 = !{!"OUT", i64 0, i64 0, i64 17, ptr null, i64 3}
  !5 = !{!"IN", i64 0, i64 19, i64 0, ptr null, i64 4}
...
---
name:            ExampleCam.updateThread
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
  - { id: 11, class: _, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 13, class: _, preferred-register: '', flags: [  ] }
  - { id: 14, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 15, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 16, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 17, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 18, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 19, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 20, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 21, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 22, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 23, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 24, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 25, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 26, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 27, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 28, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 29, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 30, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 31, class: anyregcls, preferred-register: '', flags: [  ] }
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
    %27:anyregcls(s17) = HWTFPGA_MUX i17 0
    %28:anyregcls(s17) = HWTFPGA_MUX i17 0
    %29:anyregcls(s17) = HWTFPGA_MUX i17 0
    %30:anyregcls(s17) = HWTFPGA_MUX i17 0
    %31:anyregcls(s68) = HWTFPGA_MERGE_VALUES %27(s17), %28(s17), %29(s17), %30(s17), 17, 17, 17, 17
  
  bb.1.blockL210i0_210:
    successors: %bb.1(0x80000000)
  
    %27:anyregcls(s17) = HWTFPGA_EXTRACT %31(s68), 68, 0, 17
    %28:anyregcls(s17) = HWTFPGA_EXTRACT %31(s68), 68, 17, 17
    %29:anyregcls(s17) = HWTFPGA_EXTRACT %31(s68), 68, 34, 17
    %30:anyregcls(s17) = HWTFPGA_EXTRACT %31(s68), 68, 51, 17
    HWTFPGA_CSTORE %27(s17), %0, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_0, align 4, addrspace 1)
    HWTFPGA_CSTORE %28(s17), %1, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_1, align 4, addrspace 2)
    HWTFPGA_CSTORE %29(s17), %2, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_2, align 4, addrspace 3)
    HWTFPGA_CSTORE %30(s17), %3, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_3, align 4, addrspace 4)
    %9:anyregcls(s19) = HWTFPGA_CLOAD %4, 0, 19, 1 :: (volatile load (s19) from %ir.write, align 4, addrspace 5)
    %10:anyregcls(s17) = HWTFPGA_EXTRACT %9(s19), 19, 2, 17
    %12:anyregcls(s2) = HWTFPGA_EXTRACT %9(s19), 19, 0, 2
    %15:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 0
    %18:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 1
    %21:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 -2
    %24:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 -1
    %27:anyregcls(s17) = HWTFPGA_MUX %10(s17), %15(s1), %27(s17)
    %28:anyregcls(s17) = HWTFPGA_MUX %10(s17), %18(s1), %28(s17)
    %29:anyregcls(s17) = HWTFPGA_MUX %10(s17), %21(s1), %29(s17)
    %30:anyregcls(s17) = HWTFPGA_MUX %10(s17), %24(s1), %30(s17)
    %31:anyregcls(s68) = HWTFPGA_MERGE_VALUES %27(s17), %28(s17), %29(s17), %30(s17), 17, 17, 17, 17
    HWTFPGA_BR %bb.1
...
--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCam.matchThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %match, ptr addrspace(6) %out) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_24
  
  blockL24i0_24:                                    ; preds = %bb0, %blockL24i0_24
    %match_read1 = load volatile i16, ptr addrspace(5) %match, align 2
    %keyForMatchThread_0_read1 = load volatile i17, ptr addrspace(1) %keyForMatchThread_0, align 4
    %keyForMatchThread_0_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_0_read1, i6 16) #1
    %keyForMatchThread_0_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_0_read1, i6 0) #1
    %keyForMatchThread_1_read1 = load volatile i17, ptr addrspace(2) %keyForMatchThread_1, align 4
    %keyForMatchThread_1_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_1_read1, i6 16) #1
    %keyForMatchThread_1_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_1_read1, i6 0) #1
    %keyForMatchThread_2_read1 = load volatile i17, ptr addrspace(3) %keyForMatchThread_2, align 4
    %keyForMatchThread_2_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_2_read1, i6 16) #1
    %keyForMatchThread_2_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_2_read1, i6 0) #1
    %keyForMatchThread_3_read1 = load volatile i17, ptr addrspace(4) %keyForMatchThread_3, align 4
    %keyForMatchThread_3_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_3_read1, i6 16) #1
    %keyForMatchThread_3_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_3_read1, i6 0) #1
    %0 = icmp eq i16 %keyForMatchThread_3_read_key3, %match_read1
    %1 = icmp eq i16 %keyForMatchThread_2_read_key3, %match_read1
    %2 = icmp eq i16 %keyForMatchThread_1_read_key3, %match_read1
    %3 = icmp eq i16 %keyForMatchThread_0_read_key3, %match_read1
    %4 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %keyForMatchThread_0_read_vld4, i1 %keyForMatchThread_1_read_vld4, i1 %keyForMatchThread_2_read_vld4, i1 %keyForMatchThread_3_read_vld4) #1
    %5 = call i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1 %3, i1 %2, i1 %1, i1 %0) #1
    %.opConc = and i4 %4, %5
    store volatile i4 %.opConc, ptr addrspace(6) %out, align 1
    br label %blockL24i0_24
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17, i6) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17, i6) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitConcat.i1.i1.i1.i1(i1, i1, i1, i1) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2, !3, !4, !5, !6}
  !1 = !{!"IN", i64 0, i64 17, i64 0, ptr null, i64 0}
  !2 = !{!"IN", i64 0, i64 17, i64 0, ptr null, i64 1}
  !3 = !{!"IN", i64 0, i64 17, i64 0, ptr null, i64 2}
  !4 = !{!"IN", i64 0, i64 17, i64 0, ptr null, i64 3}
  !5 = !{!"IN", i64 0, i64 16, i64 0, ptr null, i64 4}
  !6 = !{!"OUT", i64 0, i64 0, i64 4, ptr null, i64 5}
...
---
name:            ExampleCam.matchThread
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
  - { id: 9, class: _, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 11, class: _, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 13, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 14, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 15, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 16, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 17, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 18, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 19, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 20, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 21, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 22, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 23, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 24, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 25, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 26, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 27, class: anyregcls, preferred-register: '', flags: [  ] }
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
  
  bb.1.blockL24i0_24:
    successors: %bb.1(0x80000000)
  
    %6:anyregcls(s16) = HWTFPGA_CLOAD %4, 0, 16, 1 :: (volatile load (s16) from %ir.match, addrspace 5)
    %7:anyregcls(s17) = HWTFPGA_CLOAD %0, 0, 17, 1 :: (volatile load (s17) from %ir.keyForMatchThread_0, align 4, addrspace 1)
    %8:anyregcls(s1) = HWTFPGA_EXTRACT %7(s17), 17, 16, 1
    %10:anyregcls(s16) = HWTFPGA_EXTRACT %7(s17), 17, 0, 16
    %12:anyregcls(s17) = HWTFPGA_CLOAD %1, 0, 17, 1 :: (volatile load (s17) from %ir.keyForMatchThread_1, align 4, addrspace 2)
    %13:anyregcls(s1) = HWTFPGA_EXTRACT %12(s17), 17, 16, 1
    %14:anyregcls(s16) = HWTFPGA_EXTRACT %12(s17), 17, 0, 16
    %15:anyregcls(s17) = HWTFPGA_CLOAD %2, 0, 17, 1 :: (volatile load (s17) from %ir.keyForMatchThread_2, align 4, addrspace 3)
    %16:anyregcls(s1) = HWTFPGA_EXTRACT %15(s17), 17, 16, 1
    %17:anyregcls(s16) = HWTFPGA_EXTRACT %15(s17), 17, 0, 16
    %18:anyregcls(s17) = HWTFPGA_CLOAD %3, 0, 17, 1 :: (volatile load (s17) from %ir.keyForMatchThread_3, align 4, addrspace 4)
    %19:anyregcls(s1) = HWTFPGA_EXTRACT %18(s17), 17, 16, 1
    %20:anyregcls(s16) = HWTFPGA_EXTRACT %18(s17), 17, 0, 16
    %21:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %20(s16), %6
    %22:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %17(s16), %6
    %23:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %14(s16), %6
    %24:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %10(s16), %6
    %25:anyregcls(s4) = HWTFPGA_MERGE_VALUES %8(s1), %13(s1), %16(s1), %19(s1), 1, 1, 1, 1
    %26:anyregcls(s4) = HWTFPGA_MERGE_VALUES %24(s1), %23(s1), %22(s1), %21(s1), 1, 1, 1, 1
    %27:anyregcls(s4) = HWTFPGA_AND %25(s4), %26(s4)
    HWTFPGA_CSTORE %27(s4), %5, 0, 4, 1 :: (volatile store (s4) into %ir.out, addrspace 6)
    HWTFPGA_BR %bb.1
...
