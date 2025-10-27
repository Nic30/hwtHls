--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @WhileAndIf4.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_L116i0_116
  
  blockL24i0_L116i0_116:                            ; preds = %blockL24i0_L116i0_116, %blockL24i0_L116i0_206, %bb0
    %x.0 = phi i8 [ 10, %bb0 ], [ %0, %blockL24i0_L116i0_206 ], [ %0, %blockL24i0_L116i0_116 ]
    %dataIn_read1 = load volatile i8, ptr addrspace(1) %dataIn, align 1
    %0 = sub i8 %x.0, %dataIn_read1
    %1 = icmp ult i8 %0, 5
    br i1 %1, label %blockL24i0_L116i0_206, label %blockL24i0_L116i0_116
  
  blockL24i0_L116i0_206:                            ; preds = %blockL24i0_L116i0_116
    store volatile i8 %0, ptr addrspace(2) %dataOut, align 1
    br label %blockL24i0_L116i0_116
  }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 8, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 1}

...
---
name:            WhileAndIf4.mainThread
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
  - { id: 5, class: anyregbank, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: _, preferred-register: '' }
  - { id: 9, class: _, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
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
    %12:anyregcls(s8) = HWTFPGA_MUX i8 10
  
  bb.1.blockL24i0_L116i0_116:
    successors: %bb.1(0x80000000)
  
    %3:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
    %12:anyregcls(s8) = HWTFPGA_SUB %12(s8), %3(s8)
    %6:anyregcls(s1) = HWTFPGA_ICMP intpred(uge), %12(s8), i8 5
    %10:anyregcls(s1) = HWTFPGA_NOT %6(s1)
    HWTFPGA_CSTORE %12(s8), %1, 0, 8, %10(s1) :: (volatile store (s8) into %ir.dataOut, addrspace 2)
    HWTFPGA_BR %bb.1

...
