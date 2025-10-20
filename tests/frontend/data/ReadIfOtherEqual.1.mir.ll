--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ReadIfOtherEqual.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
  bb0:
    br label %blockL14i0_14
  
  blockL14i0_14:                                    ; preds = %blockL14i0_14, %blockL14i0_118, %bb0
    %a_read1 = load volatile i8, ptr addrspace(1) %a, align 1
    %0 = icmp eq i8 %a_read1, 3
    br i1 %0, label %blockL14i0_118, label %blockL14i0_14
  
  blockL14i0_118:                                   ; preds = %blockL14i0_14
    %b_read1 = load volatile i8, ptr addrspace(2) %b, align 1
    br label %blockL14i0_14
  }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 0}
  !2 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 1}

...
---
name:            ReadIfOtherEqual.mainThread
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
  - { id: 6, class: _, preferred-register: '' }
  - { id: 7, class: _, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
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
  
  bb.1.blockL14i0_14:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.a, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %2(s8), i8 3
    %8:anyregcls(s1) = HWTFPGA_NOT %4(s1)
    dead %5:anyregcls(s8) = HWTFPGA_CLOAD %1, 0, 8, %8(s1) :: (volatile load (s8) from %ir.b, addrspace 2)
    HWTFPGA_BR %bb.1

...
