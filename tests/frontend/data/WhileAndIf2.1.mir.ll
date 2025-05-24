--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @WhileAndIf2.mainThread(ptr addrspace(1) %dataIn, ptr addrspace(2) %dataOut) !hwtHls.param_addr_width !0 {
  bb0:
    br label %blockL14i0_14
  
  blockL14i0_14:                                    ; preds = %blockL14i0_L94i0_94, %bb0
    br label %blockL14i0_L94i0_94
  
  blockL14i0_L94i0_94:                              ; preds = %blockL14i0_L94i0_94, %blockL14i0_14
    %x.0 = phi i8 [ 10, %blockL14i0_14 ], [ %0, %blockL14i0_L94i0_94 ]
    %dataIn_read1 = load volatile i8, ptr addrspace(1) %dataIn, align 1
    %0 = sub i8 %x.0, %dataIn_read1
    store volatile i8 %0, ptr addrspace(2) %dataOut, align 1
    %.not = icmp eq i8 %0, 0
    br i1 %.not, label %blockL14i0_14, label %blockL14i0_L94i0_94
  }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}

...
---
name:            WhileAndIf2.mainThread
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
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
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
    %8:anyregcls(s8) = HWTFPGA_MUX i8 10
  
  bb.1.blockL14i0_L94i0_94:
    successors: %bb.1(0x80000000)
  
    %3:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.dataIn, addrspace 1)
    %8:anyregcls(s8) = HWTFPGA_SUB %8(s8), %3(s8)
    HWTFPGA_CSTORE %8(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 2)
    %6:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %8(s8), i8 0
    %9:anyregcls(s1) = HWTFPGA_NOT %6(s1)
    %11:anyregcls(s1) = HWTFPGA_NOT %9(s1)
    %8:anyregcls(s8) = HWTFPGA_MUX i8 10, %11(s1), %8(s8)
    HWTFPGA_BR %bb.1

...
