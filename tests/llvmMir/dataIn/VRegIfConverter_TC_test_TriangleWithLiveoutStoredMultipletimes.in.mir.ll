--- |
  ; ModuleID = 'VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes'
  source_filename = "VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes(i1 addrspace(2)* %iC0, i8 addrspace(3)* %o) {
  test_TriangleWithLiveoutStoredMultipletimes:
    br label %EBB
  
  EBB:
    br label %TBB
  
  TBB:
    br label %FBB
  
  FBB:
    ret void
  }

...
---
name:            VRegIfConverter_TC_test_TriangleWithLiveoutStoredMultipletimes
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
  bb.0.test_TriangleWithLiveoutStoredMultipletimes:
    successors: %bb.1(0x80000000)
  
    %0:anyregcls = HWTFPGA_ARG_GET 0
    %1:anyregcls = HWTFPGA_ARG_GET 1
  
  bb.1.EBB:
    successors: %bb.2(0x30000000), %bb.3(0x50000000)
  
    %2:anyregcls(s1) = HWTFPGA_CLOAD %0, 0, 1, 1 :: (volatile load (s16) from %ir.iC0, addrspace 1)
    %3:anyregcls(s64) = HWTFPGA_MUX i64 0
    HWTFPGA_BRCOND %2(s1), %bb.3
  
  bb.2.TBB:
    successors: %bb.3(0x80000000)

    %3:anyregcls(s64) = HWTFPGA_MUX i64 1
    %3:anyregcls(s64) = HWTFPGA_MUX i64 3
    HWTFPGA_BR %bb.3
  
  bb.3.FBB:

    HWTFPGA_CSTORE %3(s64), %1, 0, 64, 1 :: (volatile store (s64) into %ir.o, align 4, addrspace 2)
    HWTFPGA_RET

...
