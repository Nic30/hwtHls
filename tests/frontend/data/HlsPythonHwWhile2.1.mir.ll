--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonHwWhile2.mainThread(ptr addrspace(1) %o) !hwtHls.io !0 {
  bb0:
    br label %wh0
  
  wh0:                                              ; preds = %bb0, %blockL68i0_204
    %i.0 = phi i8 [ 0, %bb0 ], [ %2, %blockL68i0_204 ]
    %0 = icmp ult i8 %i.0, 5
    %1 = icmp eq i8 %i.0, 10
    br i1 %0, label %blockL68i0_102, label %blockL68i0_158
  
  blockL68i0_102:                                   ; preds = %wh0
    store volatile i8 %i.0, ptr addrspace(1) %o, align 1
    br label %blockL68i0_204
  
  blockL68i0_204:                                   ; preds = %blockL68i0_158, %blockL68i0_102
    %2 = add i8 %i.0, 1
    br label %wh0
  
  blockL68i0_158:                                   ; preds = %wh0
    br i1 %1, label %wh1.preheader, label %blockL68i0_204
  
  wh1.preheader:                                    ; preds = %blockL68i0_158
    br label %wh1
  
  wh1:                                              ; preds = %wh1.preheader, %wh1
    store volatile i8 0, ptr addrspace(1) %o, align 1
    br label %wh1
  }
  
  !0 = distinct !{!1}
  !1 = !{!"OUT", i64 0, i64 0, i64 8, ptr null, i64 0}
...
---
name:            HlsPythonHwWhile2.mainThread
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
  - { id: 2, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 3, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 4, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 7, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 9, class: _, preferred-register: '', flags: [  ] }
  - { id: 10, class: _, preferred-register: '', flags: [  ] }
  - { id: 11, class: _, preferred-register: '', flags: [  ] }
  - { id: 12, class: _, preferred-register: '', flags: [  ] }
  - { id: 13, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 14, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 15, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 16, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 17, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 18, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 19, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 20, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 21, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 22, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 23, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 24, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 25, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 26, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 27, class: anyregcls, preferred-register: '', flags: [  ] }
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
  isCalleeSavedInfoValid: false
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
    %13:anyregcls(s8) = HWTFPGA_MUX i8 0
  
  bb.1.wh0:
    successors: %bb.2(0x02000000), %bb.1(0x7e000000)
  
    %3:anyregcls(s1) = HWTFPGA_ICMP intpred(uge), %13(s8), i8 5
    %18:anyregcls(s1) = HWTFPGA_NOT %3(s1)
    HWTFPGA_CSTORE %13(s8), %0, 0, 8, %18(s1) :: (volatile store (s8) into %ir.o, addrspace 1)
    %5:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %13(s8), i8 10
    %20:anyregcls(s1) = HWTFPGA_NOT %5(s1)
    %22:anyregcls(s1) = HWTFPGA_AND %3(s1), %20(s1)
    %23:anyregcls(s8) = HWTFPGA_ADD %13(s8), i8 1
    %13:anyregcls(s8) = HWTFPGA_MUX %13(s8), %22(s1), %23(s8)
    HWTFPGA_BRCOND %22(s1), %bb.2
    HWTFPGA_BR %bb.1
  
  bb.2.wh1:
    successors: %bb.2(0x80000000)
  
    HWTFPGA_CSTORE i8 0, %0, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 1)
    HWTFPGA_BR %bb.2
...
