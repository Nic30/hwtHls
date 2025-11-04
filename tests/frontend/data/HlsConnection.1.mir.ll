--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsConnection.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_24
  
  blockL24i0_24:                                    ; preds = %bb0, %blockL24i0_24
    %a_read1 = load volatile i32, ptr addrspace(1) %a, align 4
    store volatile i32 %a_read1, ptr addrspace(2) %b, align 4
    br label %blockL24i0_24
  }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 32, ptr null, i64 1}
...
---
name:            HlsConnection.mainThread
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
  
    %2:anyregcls(s32) = HWTFPGA_CLOAD %0, 0, 32, 1 :: (volatile load (s32) from %ir.a, addrspace 1)
    HWTFPGA_CSTORE %2(s32), %1, 0, 32, 1 :: (volatile store (s32) into %ir.b, addrspace 2)
    HWTFPGA_BR %bb.1
...
