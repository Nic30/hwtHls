--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @TwoTimesA1.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_24
  
  blockL24i0_24:                                    ; preds = %bb0, %blockL24i0_24
    %a_read2 = load volatile i8, ptr addrspace(1) %a, align 1
    %0 = call i7 @hwtHls.bitRangeGet.i8.i4.i7.0(i8 %a_read2, i4 0) #1
    %1 = call i8 @hwtHls.bitConcat.i1.i7(i1 false, i7 %0) #1
    store volatile i8 %1, ptr addrspace(2) %b, align 1
    br label %blockL24i0_24
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i7 @hwtHls.bitRangeGet.i8.i4.i7.0(i8, i4) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitConcat.i1.i7(i1, i7) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 1}
...
---
name:            TwoTimesA1.mainThread
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
  - { id: 4, class: _, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
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
  
  bb.1.blockL24i0_24:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.a, addrspace 1)
    %3:anyregcls(s7) = HWTFPGA_EXTRACT %2(s8), 8, 0, 7
    %5:anyregcls(s8) = HWTFPGA_MERGE_VALUES i1 false, %3(s7), 1, 7
    HWTFPGA_CSTORE %5(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.b, addrspace 2)
    HWTFPGA_BR %bb.1
...
