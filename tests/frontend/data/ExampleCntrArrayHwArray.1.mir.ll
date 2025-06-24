--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCntrArrayHwArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %o_addr) !hwtHls.io !0 {
  bb0:
    br label %blockL180i0_180
  
  blockL180i0_180:                                  ; preds = %bb0, %blockL180i0_180
    %o_addr_read1 = load volatile i2, ptr addrspace(3) %o_addr, align 1
    %i_read2 = load volatile i2, ptr addrspace(1) %i, align 1
    store volatile i16 0, ptr addrspace(2) %o, align 2
    br label %blockL180i0_180
  }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2, !3, !4}
  !2 = !{!"IN", i64 0, ptr null, i64 0}
  !3 = !{!"OUT", i64 0, ptr null, i64 1}
  !4 = !{!"IN", i64 0, ptr null, i64 2}

...
---
name:            ExampleCntrArrayHwArray.mainThread
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
  
  bb.1.blockL180i0_180:
    successors: %bb.1(0x80000000)
  
    dead %3:anyregcls(s2) = HWTFPGA_CLOAD %2, 0, 2, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 3)
    dead %4:anyregcls(s2) = HWTFPGA_CLOAD %0, 0, 2, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
    HWTFPGA_CSTORE i16 0, %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

...
