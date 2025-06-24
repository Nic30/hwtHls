--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) !hwtHls.io !0 {
  bb0:
    br label %blockL192i0_192
  
  blockL192i0_192:                                  ; preds = %bb0, %blockL192i0_192
    %.phiConc = phi i17 [ 0, %bb0 ], [ %.selConc, %blockL192i0_192 ]
    %.phiConc41 = phi i17 [ 0, %bb0 ], [ %.selConc42, %blockL192i0_192 ]
    %.phiConc43 = phi i17 [ 0, %bb0 ], [ %.selConc44, %blockL192i0_192 ]
    %.phiConc45 = phi i17 [ 0, %bb0 ], [ %.selConc46, %blockL192i0_192 ]
    store volatile i17 %.phiConc, ptr addrspace(1) %keyForMatchThread_0, align 4
    store volatile i17 %.phiConc41, ptr addrspace(2) %keyForMatchThread_1, align 4
    store volatile i17 %.phiConc43, ptr addrspace(3) %keyForMatchThread_2, align 4
    store volatile i17 %.phiConc45, ptr addrspace(4) %keyForMatchThread_3, align 4
    %write_read1 = load volatile i19, ptr addrspace(5) %write, align 4
    %0 = call i17 @hwtHls.bitRangeGet.i19.i6.i17.2(i19 %write_read1, i6 2) #1
    %write_read_addr3 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read1, i6 0) #1
    %1 = icmp eq i2 %write_read_addr3, 0
    %.selConc = select i1 %1, i17 %0, i17 %.phiConc
    %2 = icmp eq i2 %write_read_addr3, -1
    %.selConc46 = select i1 %2, i17 %0, i17 %.phiConc45
    %3 = icmp eq i2 %write_read_addr3, 1
    %.selConc42 = select i1 %3, i17 %0, i17 %.phiConc41
    %4 = icmp eq i2 %write_read_addr3, -2
    %.selConc44 = select i1 %4, i17 %0, i17 %.phiConc43
    br label %blockL192i0_192
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19, i6) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i17 @hwtHls.bitRangeGet.i19.i6.i17.2(i19, i6) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2, !3, !4, !5, !6}
  !2 = !{!"OUT", i64 0, ptr null, i64 0}
  !3 = !{!"OUT", i64 0, ptr null, i64 1}
  !4 = !{!"OUT", i64 0, ptr null, i64 2}
  !5 = !{!"OUT", i64 0, ptr null, i64 3}
  !6 = !{!"IN", i64 0, ptr null, i64 4}

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
  - { id: 11, class: _, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: _, preferred-register: '' }
  - { id: 14, class: anyregbank, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
  - { id: 16, class: anyregcls, preferred-register: '' }
  - { id: 17, class: anyregbank, preferred-register: '' }
  - { id: 18, class: anyregcls, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregbank, preferred-register: '' }
  - { id: 21, class: anyregcls, preferred-register: '' }
  - { id: 22, class: anyregcls, preferred-register: '' }
  - { id: 23, class: anyregbank, preferred-register: '' }
  - { id: 24, class: anyregcls, preferred-register: '' }
  - { id: 25, class: anyregcls, preferred-register: '' }
  - { id: 26, class: anyregcls, preferred-register: '' }
  - { id: 27, class: anyregcls, preferred-register: '' }
  - { id: 28, class: anyregcls, preferred-register: '' }
  - { id: 29, class: anyregcls, preferred-register: '' }
  - { id: 30, class: anyregcls, preferred-register: '' }
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
    %27:anyregcls(s17) = HWTFPGA_MUX i17 0
    %28:anyregcls(s17) = HWTFPGA_MUX i17 0
    %29:anyregcls(s17) = HWTFPGA_MUX i17 0
    %30:anyregcls(s17) = HWTFPGA_MUX i17 0
  
  bb.1.blockL192i0_192:
    successors: %bb.1(0x80000000)
  
    HWTFPGA_CSTORE %27(s17), %0, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_0, align 4, addrspace 1)
    HWTFPGA_CSTORE %28(s17), %1, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_1, align 4, addrspace 2)
    HWTFPGA_CSTORE %29(s17), %2, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_2, align 4, addrspace 3)
    HWTFPGA_CSTORE %30(s17), %3, 0, 17, 1 :: (volatile store (s17) into %ir.keyForMatchThread_3, align 4, addrspace 4)
    %9:anyregcls(s19) = HWTFPGA_CLOAD %4, 0, 19, 1 :: (volatile load (s19) from %ir.write, align 4, addrspace 5)
    %10:anyregcls(s17) = HWTFPGA_EXTRACT %9(s19), 19, 2, 17
    %12:anyregcls(s2) = HWTFPGA_EXTRACT %9(s19), 19, 0, 2
    %15:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 0
    %18:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 -1
    %21:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 1
    %24:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %12(s2), i2 -2
    %27:anyregcls(s17) = HWTFPGA_MUX %10(s17), %15(s1), %27(s17)
    %28:anyregcls(s17) = HWTFPGA_MUX %10(s17), %21(s1), %28(s17)
    %29:anyregcls(s17) = HWTFPGA_MUX %10(s17), %24(s1), %29(s17)
    %30:anyregcls(s17) = HWTFPGA_MUX %10(s17), %18(s1), %30(s17)
    HWTFPGA_BR %bb.1

...
