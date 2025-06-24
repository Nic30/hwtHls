--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @WhileAndIf0.mainThread(ptr addrspace(1) %dataOut) !hwtHls.io !0 {
  bb0:
    br label %blockL14i0_14
  
  blockL14i0_14:                                    ; preds = %blockL14i0_L94i0_94, %bb0
    br label %blockL14i0_L94i0_94
  
  blockL14i0_L94i0_94:                              ; preds = %blockL14i0_L94i0_94, %blockL14i0_14
    %x.0 = phi i8 [ 10, %blockL14i0_14 ], [ %., %blockL14i0_L94i0_94 ]
    %0 = icmp ult i8 %x.0, 3
    %1 = call i8 @hwtHls.bitConcat.i1.i1.i6(i1 true, i1 %0, i6 -1) #1
    %. = add i8 %1, %x.0
    store volatile i8 %., ptr addrspace(1) %dataOut, align 1
    %.not = icmp eq i8 %., 0
    br i1 %.not, label %blockL14i0_14, label %blockL14i0_L94i0_94
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitConcat.i1.i1.i6(i1, i1, i6) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2}
  !2 = !{!"OUT", i64 0, ptr null, i64 0}

...
---
name:            WhileAndIf0.mainThread
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
  - { id: 4, class: anyregcls, preferred-register: '' }
  - { id: 5, class: anyregcls, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregbank, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
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
    %11:anyregcls(s8) = HWTFPGA_MUX i8 10
  
  bb.1.blockL14i0_L94i0_94:
    successors: %bb.1(0x80000000)
  
    %3:anyregcls(s1) = HWTFPGA_ICMP intpred(ult), %11(s8), i8 3
    %4:anyregcls(s8) = HWTFPGA_MERGE_VALUES i1 true, %3(s1), i6 -1, 1, 1, 6
    %7:anyregcls(s8) = HWTFPGA_ADD %4(s8), %11(s8)
    HWTFPGA_CSTORE %7(s8), %0, 0, 8, 1 :: (volatile store (s8) into %ir.dataOut, addrspace 1)
    %9:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %7(s8), i8 0
    %12:anyregcls(s1) = HWTFPGA_NOT %9(s1)
    %14:anyregcls(s1) = HWTFPGA_NOT %12(s1)
    %11:anyregcls(s8) = HWTFPGA_MUX i8 10, %14(s1), %7(s8)
    HWTFPGA_BR %bb.1

...
