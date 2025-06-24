--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsConnectionFromPyIfElifElse.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
    %switch.selectcmp = icmp eq i8 %i_read1, 10
    %switch.selectcmp2 = icmp eq i8 %i_read1, 2
    %0 = call i2 @hwtHls.bitConcat.i1.i1(i1 %switch.selectcmp, i1 true) #1
    %switch.select34 = select i1 %switch.selectcmp2, i2 1, i2 %0
    %1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %switch.select34, i2 1) #1
    %2 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %switch.select34, i2 0) #1
    %3 = call i8 @hwtHls.bitConcat.i1.i2.i1.i4(i1 %2, i2 1, i1 %1, i4 0) #1
    store volatile i8 %3, ptr addrspace(2) %o, align 1
    ret void
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitConcat.i1.i1(i1, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitConcat.i1.i2.i1.i4(i1, i2, i1, i4) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2, !3}
  !2 = !{!"IN", i64 0, ptr null, i64 0}
  !3 = !{!"OUT", i64 0, ptr null, i64 1}

...
---
name:            HlsConnectionFromPyIfElifElse.mainThread
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
  - { id: 3, class: anyregbank, preferred-register: '' }
  - { id: 4, class: anyregcls, preferred-register: '' }
  - { id: 5, class: anyregbank, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: _, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
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
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
    %2:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s8), i8 10
    %6:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s8), i8 2
    %7:anyregcls(s2) = HWTFPGA_MERGE_VALUES %4(s1), i1 true, 1, 1
    %9:anyregcls(s2) = HWTFPGA_MUX i2 1, %6(s1), %7(s2)
    %11:anyregcls(s1) = HWTFPGA_EXTRACT %9(s2), 2, 1, 1
    %12:anyregcls(s1) = HWTFPGA_EXTRACT %9(s2), 2, 0, 1
    %14:anyregcls(s8) = HWTFPGA_MERGE_VALUES %12(s1), i2 1, %11(s1), i4 0, 1, 2, 1, 4
    HWTFPGA_CSTORE %14(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
    HWTFPGA_RET

...
