--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonSwap.mainThread(ptr addrspace(1) %i0, ptr addrspace(2) %i1, ptr addrspace(3) %o0, ptr addrspace(4) %o1, ptr addrspace(5) %swap) !hwtHls.param_addr_width !0 {
  bb0:
    br label %blockL14i0_14
  
  blockL14i0_14:                                    ; preds = %bb0, %blockL14i0_14
    %swap_read2 = load volatile i1, ptr addrspace(5) %swap, align 1
    %i0_read2 = load volatile i8, ptr addrspace(1) %i0, align 1
    %i1_read2 = load volatile i8, ptr addrspace(2) %i1, align 1
    %i01.0 = select i1 %swap_read2, i8 %i1_read2, i8 %i0_read2
    %i11.0 = select i1 %swap_read2, i8 %i0_read2, i8 %i1_read2
    store volatile i8 %i01.0, ptr addrspace(3) %o0, align 1
    store volatile i8 %i11.0, ptr addrspace(4) %o1, align 1
    br label %blockL14i0_14
  }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0, i32 0, i32 0, i32 0}

...
---
name:            HlsPythonSwap.mainThread
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
  - { id: 5, class: anyregcls, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
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
    %2:anyregcls = HWTFPGA_ARG_GET 2
    %3:anyregcls = HWTFPGA_ARG_GET 3
    %4:anyregcls = HWTFPGA_ARG_GET 4
  
  bb.1.blockL14i0_14:
    successors: %bb.1(0x80000000)
  
    %5:anyregcls(s1) = HWTFPGA_CLOAD %4, 0, 1, 1 :: (volatile load (s1) from %ir.swap, addrspace 5)
    %6:anyregcls(s8) = HWTFPGA_CLOAD %0, 0, 8, 1 :: (volatile load (s8) from %ir.i0, addrspace 1)
    %7:anyregcls(s8) = HWTFPGA_CLOAD %1, 0, 8, 1 :: (volatile load (s8) from %ir.i1, addrspace 2)
    %8:anyregcls(s8) = HWTFPGA_MUX %7(s8), %5(s1), %6(s8)
    %9:anyregcls(s8) = HWTFPGA_MUX %6(s8), %5(s1), %7(s8)
    HWTFPGA_CSTORE %8(s8), %2, 0, 8, 1 :: (volatile store (s8) into %ir.o0, addrspace 3)
    HWTFPGA_CSTORE %9(s8), %3, 0, 8, 1 :: (volatile store (s8) into %ir.o1, addrspace 4)
    HWTFPGA_BR %bb.1

...
