--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @VRegIfConverter_TC_test_for2add(ptr addrspace(2) %data_out) {
  bb0:
    br label %bb2
  
  bb2: ; preds = %bb0
    br label %bb3
  
  bb3: ; preds = %bb2, %bb3
    %v.0 = phi i3 [ %v.1, %bb3 ], [ 0, %bb2 ]
    %i = phi i1 [ 1, %bb3 ], [ 0, %bb2 ]
    %v.1 = add nuw i3 %v.0, 1
    br i1 %i, label %bb4, label %bb3
  
  bb4:                        ; preds = %bb3
    store volatile i3 %v.1, ptr addrspace(2) %data_out, align 1
    br label %bb2

  }

...
---
name:            VRegIfConverter_TC_test_for2add
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
  - { id: 3, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 4, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
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
    successors: %bb.2(0x80000000); %bb.2(100.00%)
  
    %1:anyregcls = HWTFPGA_ARG_GET 0
    %3:anyregcls = HWTFPGA_MUX i3 1
  
  bb.2.bb2:
  ; predecessors: %bb.0
    successors: %bb.3(0x80000000); %bb.3(100.00%)
  
    %4:anyregcls = HWTFPGA_MUX i3 0
    %5:anyregcls = HWTFPGA_MUX i1 false
  
  bb.3.bb3:
  ; predecessors: %bb.2, %bb.3
    successors: %bb.4(0x04000000), %bb.3(0x7c000000); %bb.4(3.12%), %bb.3(96.88%)
    
    %4:anyregcls = HWTFPGA_ADD killed %4:anyregcls, %3:anyregcls
    %6:anyregcls = HWTFPGA_NOT killed %5:anyregcls
    %5:anyregcls = HWTFPGA_MUX i1 true
    HWTFPGA_BRCOND killed %6:anyregcls, %bb.3
  
  bb.4.bb4:
  ; predecessors: %bb.3
    successors: %bb.2(0x80000000); %bb.2(100.00%)
  
    HWTFPGA_CSTORE killed %4:anyregcls, %1:anyregcls, 0, 3, 1 :: (volatile store (s3) into %ir.data_out, addrspace 2)
    HWTFPGA_BR %bb.2

...
