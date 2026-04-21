--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonTupleAssign.mainThread(ptr addrspace(1) %o0, ptr addrspace(2) %o1) !hwtHls.io !0 {
  bb0:
    br label %blockL112i0_112
  
  blockL112i0_112:                                  ; preds = %bb0, %blockL112i0_112
    %i.shiftPhi1 = phi i2 [ %4, %blockL112i0_112 ], [ 1, %bb0 ]
    %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %i.shiftPhi1, i2 0) #1
    %1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %i.shiftPhi1, i2 1) #1
    %2 = zext i1 %1 to i8
    store volatile i8 %2, ptr addrspace(1) %o0, align 1
    %3 = zext i1 %0 to i8
    store volatile i8 %3, ptr addrspace(2) %o1, align 1
    %4 = call i2 @hwtHls.bitConcat.i1.i1(i1 %1, i1 %0) #1
    br label %blockL112i0_112
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitConcat.i1.i1(i1, i1) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 1}
...
---
name:            HlsPythonTupleAssign.mainThread
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
  - { id: 7, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregcls, preferred-register: '', flags: [  ] }
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
    %10:anyregcls(s2) = HWTFPGA_MUX i2 1
  
  bb.1.blockL112i0_112:
    successors: %bb.1(0x80000000)
  
    %3:anyregcls(s1) = HWTFPGA_EXTRACT %10(s2), 2, 0, 1
    %5:anyregcls(s1) = HWTFPGA_EXTRACT %10(s2), 2, 1, 1
    %7:anyregcls(s8) = HWTFPGA_MERGE_VALUES %5(s1), i7 0, 1, 7
    HWTFPGA_CSTORE %7(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o0, addrspace 1)
    %8:anyregcls(s8) = HWTFPGA_MERGE_VALUES %3(s1), i7 0, 1, 7
    HWTFPGA_CSTORE %8(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.o1, addrspace 2)
    %9:anyregcls(s2) = HWTFPGA_MERGE_VALUES %5(s1), %3(s1), 1, 1
    %10:anyregcls(s2) = HWTFPGA_MUX %9(s2)
    HWTFPGA_BR %bb.1
...
