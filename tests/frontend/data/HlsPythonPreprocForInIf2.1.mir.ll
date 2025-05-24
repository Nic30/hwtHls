--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonPreprocForInIf2.mainThread(ptr addrspace(1) %o) !hwtHls.param_addr_width !0 {
  bb0:
    br label %blockL110i0_110
  
  blockL110i0_110:                                  ; preds = %bb0, %exit
    %cntr.0 = phi i8 [ 0, %bb0 ], [ %1, %exit ]
    store volatile i8 %cntr.0, ptr addrspace(1) %o, align 1
    %0 = icmp eq i8 %cntr.0, 2
    br i1 %0, label %exit, label %for.head2
  
  for.head2:                                        ; preds = %blockL110i0_110
    store volatile i8 %cntr.0, ptr addrspace(1) %o, align 1
    br label %exit
  
  exit:                                             ; preds = %for.head2, %blockL110i0_110
    store volatile i8 %cntr.0, ptr addrspace(1) %o, align 1
    %1 = add i8 %cntr.0, 1
    br label %blockL110i0_110
  }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0}

...
---
name:            HlsPythonPreprocForInIf2.mainThread
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
  - { id: 2, class: anyregbank, preferred-register: '' }
  - { id: 3, class: anyregcls, preferred-register: '' }
  - { id: 4, class: anyregbank, preferred-register: '' }
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
    %9:anyregcls(s8) = HWTFPGA_MUX i8 0
  
  bb.1.blockL110i0_110:
    successors: %bb.1(0x80000000)
  
    HWTFPGA_CSTORE %9(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    %3:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %9(s8), i8 2
    %7:anyregcls(s1) = HWTFPGA_NOT %3(s1)
    HWTFPGA_CSTORE %9(s8), %0, 0, 8, %7(s1) :: (volatile store (s8) into %ir.o, addrspace 1)
    HWTFPGA_CSTORE %9(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    %5:anyregcls(s8) = HWTFPGA_ADD %9(s8), i8 1
    %9:anyregcls(s8) = HWTFPGA_MUX %5(s8)
    HWTFPGA_BR %bb.1

...
