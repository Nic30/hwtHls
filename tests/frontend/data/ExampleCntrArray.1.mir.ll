--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCntrArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %o_addr) !hwtHls.io !0 {
  bb0:
    br label %blockL210i0_210
  
  blockL210i0_210:                                  ; preds = %bb0, %blockL210i0_210
    %v3.0 = phi i16 [ %v3.1, %blockL210i0_210 ], [ 0, %bb0 ]
    %v2.0 = phi i16 [ %v2.1, %blockL210i0_210 ], [ 0, %bb0 ]
    %v1.0 = phi i16 [ %v1.1, %blockL210i0_210 ], [ 0, %bb0 ]
    %v0.0 = phi i16 [ %v0.1, %blockL210i0_210 ], [ 0, %bb0 ]
    %o_addr_read1 = load volatile i2, ptr addrspace(3) %o_addr, align 1
    %0 = icmp eq i2 %o_addr_read1, 0
    %1 = icmp eq i2 %o_addr_read1, 1
    %2 = icmp eq i2 %o_addr_read1, -2
    %3 = select i1 %2, i16 %v2.0, i16 %v3.0
    %4 = select i1 %1, i16 %v1.0, i16 %3
    %o7 = select i1 %0, i16 %v0.0, i16 %4
    store volatile i16 %o7, ptr addrspace(2) %o, align 2
    %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
    %5 = icmp eq i2 %i_read1, 0
    %6 = icmp eq i2 %i_read1, 1
    %7 = icmp eq i2 %i_read1, -2
    %8 = select i1 %7, i16 %v2.0, i16 %v3.0
    %9 = select i1 %6, i16 %v1.0, i16 %8
    %10 = select i1 %5, i16 %v0.0, i16 %9
    %11 = add i16 %10, 1
    %v0.1 = select i1 %5, i16 %11, i16 %v0.0
    %v1.1 = select i1 %6, i16 %11, i16 %v1.0
    %12 = select i1 %7, i16 %11, i16 %v2.0
    %v2.1 = select i1 %6, i16 %v2.0, i16 %12
    %fewExitSw.sucSel.en.blockL210i0_210.blockL210i0_210_434_c3 = icmp eq i2 %i_read1, -1
    %v3.1 = select i1 %fewExitSw.sucSel.en.blockL210i0_210.blockL210i0_210_434_c3, i16 %11, i16 %v3.0
    br label %blockL210i0_210
  }
  
  !0 = distinct !{!1, !2, !3}
  !1 = !{!"IN", i64 0, i64 2, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 16, ptr null, i64 1}
  !3 = !{!"IN", i64 0, i64 2, i64 0, ptr null, i64 2}
...
---
name:            ExampleCntrArray.mainThread
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
  - { id: 7, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 11, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregbank, preferred-register: '', flags: [  ] }
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
  - { id: 24, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 25, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 26, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 27, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 28, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 29, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 30, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 31, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 32, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 33, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 34, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 35, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 36, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 37, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 38, class: anyregcls, preferred-register: '', flags: [  ] }
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
    %1:anyregcls = HWTFPGA_ARG_GET 1
    %2:anyregcls = HWTFPGA_ARG_GET 2
    %34:anyregcls(s16) = HWTFPGA_MUX i16 0
    %35:anyregcls(s16) = HWTFPGA_MUX i16 0
    %36:anyregcls(s16) = HWTFPGA_MUX i16 0
    %37:anyregcls(s16) = HWTFPGA_MUX i16 0
    %38:anyregcls(s64) = HWTFPGA_MERGE_VALUES %34(s16), %35(s16), %36(s16), %37(s16), 16, 16, 16, 16
  
  bb.1.blockL210i0_210:
    successors: %bb.1(0x80000000)
  
    %34:anyregcls(s16) = HWTFPGA_EXTRACT %38(s64), 64, 0, 16
    %35:anyregcls(s16) = HWTFPGA_EXTRACT %38(s64), 64, 16, 16
    %36:anyregcls(s16) = HWTFPGA_EXTRACT %38(s64), 64, 32, 16
    %37:anyregcls(s16) = HWTFPGA_EXTRACT %38(s64), 64, 48, 16
    %7:anyregcls(s2) = HWTFPGA_CLOAD %2, 0, 2, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 3)
    %9:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %7(s2), i2 0
    %11:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %7(s2), i2 1
    %13:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %7(s2), i2 -2
    %16:anyregcls(s16) = HWTFPGA_MUX %37(s16), %9(s1), %36(s16), %11(s1), %35(s16), %13(s1), %34(s16)
    HWTFPGA_CSTORE %16(s16), %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    %17:anyregcls(s2) = HWTFPGA_CLOAD %0, 0, 2, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
    %18:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %17(s2), i2 0
    %19:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %17(s2), i2 1
    %20:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %17(s2), i2 -2
    %23:anyregcls(s16) = HWTFPGA_MUX %37(s16), %18(s1), %36(s16), %19(s1), %35(s16), %20(s1), %34(s16)
    %25:anyregcls(s16) = HWTFPGA_ADD %23(s16), i16 1
    %31:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %17(s2), i2 -1
    %34:anyregcls(s16) = HWTFPGA_MUX %25(s16), %31(s1), %34(s16)
    %35:anyregcls(s16) = HWTFPGA_MUX %35(s16), %19(s1), %25(s16), %20(s1), %35(s16)
    %36:anyregcls(s16) = HWTFPGA_MUX %25(s16), %19(s1), %36(s16)
    %37:anyregcls(s16) = HWTFPGA_MUX %25(s16), %18(s1), %37(s16)
    %38:anyregcls(s64) = HWTFPGA_MERGE_VALUES %34(s16), %35(s16), %36(s16), %37(s16), 16, 16, 16, 16
    HWTFPGA_BR %bb.1
...
