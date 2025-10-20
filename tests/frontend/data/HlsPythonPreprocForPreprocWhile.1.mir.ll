--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonPreprocForPreprocWhile.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_L42i0_42
  
  blockL24i0_L42i0_42:                              ; preds = %bb0, %blockL24i0_L42i0_42
    store volatile i8 0, ptr addrspace(1) %o, align 1
    br label %blockL24i0_L42i0_42
  }
  
  !0 = distinct !{!1}
  !1 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 0}

...
---
name:            HlsPythonPreprocForPreprocWhile.mainThread
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
  - { id: 1, class: anyregbank, preferred-register: '' }
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
  
  bb.1.blockL24i0_L42i0_42:
    successors: %bb.1(0x80000000)
  
    HWTFPGA_CSTORE i8 0, %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    HWTFPGA_BR %bb.1

...
