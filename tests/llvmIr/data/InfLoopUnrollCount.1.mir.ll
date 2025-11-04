--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @InfLoopUnrollCount.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %loopHeader, %bb0
    %i.0 = phi i8 [ 0, %bb0 ], [ %2, %loopHeader ]
    store volatile i8 %i.0, ptr addrspace(1) %o, align 1
    %0 = add i8 %i.0, 1
    store volatile i8 %0, ptr addrspace(1) %o, align 1
    %1 = add i8 %0, 1
    store volatile i8 %1, ptr addrspace(1) %o, align 1
    %2 = add i8 %1, 1
    br label %loopHeader, !llvm.loop !2
  }
  
  !0 = distinct !{!1}
  !1 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 0}
  !2 = distinct !{!2, !3}
  !3 = !{!"llvm.loop.unroll.disable"}
...
---
name:            InfLoopUnrollCount.mainThread
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
  - { id: 2, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 3, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 4, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 7, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregcls, preferred-register: '', flags: [  ] }
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
    %9:anyregcls(s8) = HWTFPGA_MUX i8 0
  
  bb.1.loopHeader:
    successors: %bb.1(0x80000000)
  
    HWTFPGA_CSTORE %9(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    %3:anyregcls(s8) = HWTFPGA_ADD %9(s8), i8 1
    HWTFPGA_CSTORE %3(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    %4:anyregcls(s8) = HWTFPGA_ADD %9(s8), i8 2
    HWTFPGA_CSTORE %4(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    %5:anyregcls(s8) = HWTFPGA_ADD %9(s8), i8 3
    %9:anyregcls(s8) = HWTFPGA_MUX %5(s8)
    HWTFPGA_BR %bb.1
...
