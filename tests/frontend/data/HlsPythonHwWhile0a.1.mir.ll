--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonHwWhile0a.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    br label %blockL68i0_68
  
  blockL68i0_68:                                    ; preds = %bb0, %blockL68i0_68
    %i1.0 = phi i8 [ 0, %bb0 ], [ %i1.1, %blockL68i0_68 ]
    %0 = add i8 %i1.0, 1
    store volatile i8 %0, ptr addrspace(2) %o, align 1
    %i_read3 = load volatile i1, ptr addrspace(1) %i, align 1
    %i1.1 = select i1 %i_read3, i8 0, i8 %0
    br label %blockL68i0_68
  }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 1, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 1}

...
---
name:            HlsPythonHwWhile0a.mainThread
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
  - { id: 5, class: anyregcls, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
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
    %8:anyregcls(s8) = HWTFPGA_MUX i8 0
  
  bb.1.blockL68i0_68:
    successors: %bb.1(0x80000000)
  
    %4:anyregcls(s8) = HWTFPGA_ADD %8(s8), i8 1
    HWTFPGA_CSTORE %4(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
    %5:anyregcls(s1) = HWTFPGA_CLOAD %0, 0, 1, 1 :: (volatile load (s1) from %ir.i, addrspace 1)
    %8:anyregcls(s8) = HWTFPGA_MUX i8 0, %5(s1), %4(s8)
    HWTFPGA_BR %bb.1

...
