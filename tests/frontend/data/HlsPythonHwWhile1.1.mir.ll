--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsPythonHwWhile1.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    br label %blockL56i0_56
  
  blockL56i0_56:                                    ; preds = %blockL56i0_L58i0_58, %bb0
    %i1.02 = phi i2 [ -1, %bb0 ], [ 0, %blockL56i0_L58i0_58 ]
    %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2 %i1.02, i2 0) #1
    %1 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %i1.02, i2 1) #1
    %i1.0 = call i8 @hwtHls.bitConcat.i1.i1.i1.i1.i4(i1 false, i1 %0, i1 false, i1 %1, i4 0) #1
    br label %blockL56i0_L58i0_58
  
  blockL56i0_L58i0_58:                              ; preds = %blockL56i0_L58i0_58, %blockL56i0_56
    %i1.1 = phi i8 [ %i1.0, %blockL56i0_56 ], [ %2, %blockL56i0_L58i0_58 ]
    store volatile i8 %i1.1, ptr addrspace(2) %o, align 1
    %i_read3 = load volatile i1, ptr addrspace(1) %i, align 1
    %2 = add i8 %i1.1, 1
    br i1 %i_read3, label %blockL56i0_56, label %blockL56i0_L58i0_58
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.0(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i8 @hwtHls.bitConcat.i1.i1.i1.i1.i4(i1, i1, i1, i1, i4) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{!2, !3}
  !2 = !{!"IN", i64 0, ptr null, i64 0}
  !3 = !{!"OUT", i64 0, ptr null, i64 1}

...
---
name:            HlsPythonHwWhile1.mainThread
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
  - { id: 6, class: _, preferred-register: '' }
  - { id: 7, class: anyregcls, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregbank, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
  - { id: 16, class: anyregcls, preferred-register: '' }
  - { id: 17, class: anyregcls, preferred-register: '' }
  - { id: 18, class: anyregcls, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregcls, preferred-register: '' }
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
    %15:anyregcls(s2) = HWTFPGA_MUX i2 -1
  
  bb.1.blockL56i0_56:
    successors: %bb.2(0x80000000)
  
    %3:anyregcls(s1) = HWTFPGA_EXTRACT %15(s2), 2, 0, 1
    %5:anyregcls(s1) = HWTFPGA_EXTRACT %15(s2), 2, 1, 1
    %16:anyregcls(s8) = HWTFPGA_MERGE_VALUES i1 false, %3(s1), i1 false, %5(s1), i4 0, 1, 1, 1, 1, 4
  
  bb.2.blockL56i0_L58i0_58:
    successors: %bb.1(0x04000000), %bb.2(0x7c000000)
  
    HWTFPGA_CSTORE %16(s8), %1, 0, 8, 1 :: (volatile store (s8) into %ir.o, addrspace 2)
    %11:anyregcls(s1) = HWTFPGA_CLOAD %0, 0, 1, 1 :: (volatile load (s1) from %ir.i, addrspace 1)
    %13:anyregcls(s8) = HWTFPGA_ADD %16(s8), i8 1
    %15:anyregcls(s2) = HWTFPGA_MUX i2 0
    %16:anyregcls(s8) = HWTFPGA_MUX %13(s8)
    HWTFPGA_BRCOND %11(s1), %bb.1
    HWTFPGA_BR %bb.2

...
