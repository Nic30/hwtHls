--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  @select.rom.table = private unnamed_addr constant [4 x i32] [i32 1, i32 2, i32 4, i32 8], align 1
  
  define void @ExampleRomPyList.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
  bb0:
    br label %blockL142i0_142
  
  blockL142i0_142:                                  ; preds = %bb0, %blockL142i0_142
    %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
    %0 = zext i2 %i_read1 to i64
    %select.rom.index = getelementptr inbounds [4 x i32], ptr @select.rom.table, i64 0, i64 %0
    %select.table.valo3 = load volatile i32, ptr %select.rom.index, align 4
    store volatile i32 %select.table.valo3, ptr addrspace(2) %o, align 4
    br label %blockL142i0_142
  }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}

...
---
name:            ExampleRomPyList.mainThread
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
  - { id: 5, class: _, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregbank, preferred-register: '' }
  - { id: 8, class: _, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: _, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
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
    %4:anyregcls(p0) = HWTFPGA_GLOBAL_VALUE @select.rom.table
  
  bb.1.blockL142i0_142:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s2) = HWTFPGA_CLOAD %0, 0, 2, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
    %9:anyregcls(s32) = HWTFPGA_CLOAD %4(p0), %2(s2), 32, 1 :: (volatile invariant load (s32) from %ir.select.rom.index)
    HWTFPGA_CSTORE %9(s32), %1, 0, 32, 1 :: (volatile store (s32) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

...
