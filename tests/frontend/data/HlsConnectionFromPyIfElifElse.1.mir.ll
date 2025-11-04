--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsConnectionFromPyIfElifElse.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    %i_read1 = load volatile i8, ptr addrspace(1) %i, align 1
    %0 = icmp eq i8 %i_read1, 2
    %1 = xor i1 %0, true
    %2 = icmp eq i8 %i_read1, 10
    %.sink2 = or i1 %0, %2
    %3 = call i8 @hwtHls.bitConcat.i1.i2.i1.i4(i1 %.sink2, i2 1, i1 %1, i4 0) #1
    store volatile i8 %3, ptr addrspace(2) %o, align 1
    ret void
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitConcat.i1.i2.i1.i4(i1, i2, i1, i4) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 1}
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
  - { id: 3, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 4, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 7, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 11, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregcls, preferred-register: '', flags: [  ] }
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
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
    %2:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.i, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s8), i8 2
    %6:anyregcls(s1) = HWTFPGA_NOT %4(s1)
    %8:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s8), i8 10
    %9:anyregcls(s1) = HWTFPGA_OR %4(s1), %8(s1)
    %10:anyregcls(s8) = HWTFPGA_MERGE_VALUES %9(s1), i2 1, %6(s1), i4 0, 1, 2, 1, 4
    HWTFPGA_CSTORE %10(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
    HWTFPGA_RET
...
