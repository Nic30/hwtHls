--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @ExampleCntrArray.mainThread(ptr addrspace(1) %i, ptr addrspace(2) %o, ptr addrspace(3) %o_addr) !hwtHls.io !0 {
  bb0:
    br label %blockL192i0_192.outer
  
  blockL192i0_192.outer:                            ; preds = %blockL192i0_192_428_c3, %bb0
    %v3.0.ph = phi i16 [ %11, %blockL192i0_192_428_c3 ], [ 0, %bb0 ]
    %v2.0.ph = phi i16 [ %v2.0.ph8, %blockL192i0_192_428_c3 ], [ 0, %bb0 ]
    %v1.0.ph = phi i16 [ %v1.0.ph12, %blockL192i0_192_428_c3 ], [ 0, %bb0 ]
    %v0.0.ph = phi i16 [ %v0.0, %blockL192i0_192_428_c3 ], [ 0, %bb0 ]
    br label %blockL192i0_192.outer7
  
  blockL192i0_192.outer7:                           ; preds = %blockL192i0_192.outer, %blockL192i0_192_428_c2
    %v2.0.ph8 = phi i16 [ %v2.0.ph, %blockL192i0_192.outer ], [ %11, %blockL192i0_192_428_c2 ]
    %v1.0.ph9 = phi i16 [ %v1.0.ph, %blockL192i0_192.outer ], [ %v1.0.ph12, %blockL192i0_192_428_c2 ]
    %v0.0.ph10 = phi i16 [ %v0.0.ph, %blockL192i0_192.outer ], [ %v0.0, %blockL192i0_192_428_c2 ]
    br label %blockL192i0_192.outer11
  
  blockL192i0_192.outer11:                          ; preds = %blockL192i0_192.outer7, %blockL192i0_192_428_c1
    %v1.0.ph12 = phi i16 [ %v1.0.ph9, %blockL192i0_192.outer7 ], [ %11, %blockL192i0_192_428_c1 ]
    %v0.0.ph13 = phi i16 [ %v0.0.ph10, %blockL192i0_192.outer7 ], [ %v0.0, %blockL192i0_192_428_c1 ]
    br label %blockL192i0_192
  
  blockL192i0_192:                                  ; preds = %blockL192i0_192.outer11, %blockL192i0_192
    %v0.0 = phi i16 [ %11, %blockL192i0_192 ], [ %v0.0.ph13, %blockL192i0_192.outer11 ]
    %o_addr_read1 = load volatile i2, ptr addrspace(3) %o_addr, align 1
    %0 = icmp eq i2 %o_addr_read1, 0
    %1 = icmp eq i2 %o_addr_read1, 1
    %2 = icmp eq i2 %o_addr_read1, -2
    %3 = select i1 %2, i16 %v2.0.ph8, i16 %v3.0.ph
    %4 = select i1 %1, i16 %v1.0.ph12, i16 %3
    %o7 = select i1 %0, i16 %v0.0, i16 %4
    store volatile i16 %o7, ptr addrspace(2) %o, align 2
    %i_read1 = load volatile i2, ptr addrspace(1) %i, align 1
    %5 = icmp eq i2 %i_read1, 0
    %6 = icmp eq i2 %i_read1, 1
    %7 = icmp eq i2 %i_read1, -2
    %8 = select i1 %7, i16 %v2.0.ph8, i16 %v3.0.ph
    %9 = select i1 %6, i16 %v1.0.ph12, i16 %8
    %10 = select i1 %5, i16 %v0.0, i16 %9
    %11 = add i16 %10, 1
    switch i2 %i_read1, label %blockL192i0_192.unreachabledefault [
      i2 0, label %blockL192i0_192
      i2 1, label %blockL192i0_192_428_c1
      i2 -2, label %blockL192i0_192_428_c2
      i2 -1, label %blockL192i0_192_428_c3
    ]
  
  blockL192i0_192.unreachabledefault:               ; preds = %blockL192i0_192
    unreachable
  
  blockL192i0_192_428_c1:                           ; preds = %blockL192i0_192
    br label %blockL192i0_192.outer11
  
  blockL192i0_192_428_c2:                           ; preds = %blockL192i0_192
    br label %blockL192i0_192.outer7
  
  blockL192i0_192_428_c3:                           ; preds = %blockL192i0_192
    br label %blockL192i0_192.outer
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
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
  - { id: 14, class: anyregbank, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
  - { id: 16, class: anyregbank, preferred-register: '' }
  - { id: 17, class: anyregcls, preferred-register: '' }
  - { id: 18, class: anyregbank, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregcls, preferred-register: '' }
  - { id: 21, class: anyregcls, preferred-register: '' }
  - { id: 22, class: anyregcls, preferred-register: '' }
  - { id: 23, class: anyregcls, preferred-register: '' }
  - { id: 24, class: anyregcls, preferred-register: '' }
  - { id: 25, class: anyregcls, preferred-register: '' }
  - { id: 26, class: anyregcls, preferred-register: '' }
  - { id: 27, class: anyregcls, preferred-register: '' }
  - { id: 28, class: anyregcls, preferred-register: '' }
  - { id: 29, class: anyregcls, preferred-register: '' }
  - { id: 30, class: anyregbank, preferred-register: '' }
  - { id: 31, class: anyregcls, preferred-register: '' }
  - { id: 32, class: anyregcls, preferred-register: '' }
  - { id: 33, class: anyregcls, preferred-register: '' }
  - { id: 34, class: anyregbank, preferred-register: '' }
  - { id: 35, class: anyregcls, preferred-register: '' }
  - { id: 36, class: anyregcls, preferred-register: '' }
  - { id: 37, class: anyregcls, preferred-register: '' }
  - { id: 38, class: anyregcls, preferred-register: '' }
  - { id: 39, class: anyregcls, preferred-register: '' }
  - { id: 40, class: anyregcls, preferred-register: '' }
  - { id: 41, class: anyregcls, preferred-register: '' }
  - { id: 42, class: anyregcls, preferred-register: '' }
  - { id: 43, class: anyregcls, preferred-register: '' }
  - { id: 44, class: anyregcls, preferred-register: '' }
  - { id: 45, class: anyregcls, preferred-register: '' }
  - { id: 46, class: anyregcls, preferred-register: '' }
  - { id: 47, class: anyregcls, preferred-register: '' }
  - { id: 48, class: anyregcls, preferred-register: '' }
  - { id: 49, class: anyregcls, preferred-register: '' }
  - { id: 50, class: anyregcls, preferred-register: '' }
  - { id: 51, class: anyregcls, preferred-register: '' }
  - { id: 52, class: anyregcls, preferred-register: '' }
  - { id: 53, class: anyregcls, preferred-register: '' }
  - { id: 54, class: anyregcls, preferred-register: '' }
  - { id: 55, class: anyregcls, preferred-register: '' }
  - { id: 56, class: anyregcls, preferred-register: '' }
  - { id: 57, class: anyregcls, preferred-register: '' }
  - { id: 58, class: anyregcls, preferred-register: '' }
  - { id: 59, class: anyregcls, preferred-register: '' }
  - { id: 60, class: anyregcls, preferred-register: '' }
  - { id: 61, class: anyregcls, preferred-register: '' }
  - { id: 62, class: anyregcls, preferred-register: '' }
  - { id: 63, class: anyregcls, preferred-register: '' }
  - { id: 64, class: anyregcls, preferred-register: '' }
  - { id: 65, class: anyregcls, preferred-register: '' }
  - { id: 66, class: anyregcls, preferred-register: '' }
  - { id: 67, class: anyregcls, preferred-register: '' }
  - { id: 68, class: anyregcls, preferred-register: '' }
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
    %3:anyregcls(s16) = HWTFPGA_MUX i16 0
    %7:anyregcls(s16) = HWTFPGA_MUX i16 0
    %44:anyregcls(s16) = HWTFPGA_MUX i16 0
    %12:anyregcls(s16) = HWTFPGA_MUX i16 0
    %67:anyregcls(s64) = HWTFPGA_MERGE_VALUES %3(s16), %7(s16), %12(s16), %44(s16), 16, 16, 16, 16
  
  bb.1.blockL192i0_192:
    successors: %bb.2(0x80000000)
  
    %3:anyregcls(s16) = HWTFPGA_EXTRACT %67(s64), 64, 0, 16
    %7:anyregcls(s16) = HWTFPGA_EXTRACT %67(s64), 64, 16, 16
    %12:anyregcls(s16) = HWTFPGA_EXTRACT %67(s64), 64, 32, 16
    %44:anyregcls(s16) = HWTFPGA_EXTRACT %67(s64), 64, 48, 16
    %10:anyregcls(s16) = HWTFPGA_MUX %44(s16)
    %46:anyregcls(s16) = HWTFPGA_MUX %12(s16)
    %68:anyregcls(s64) = HWTFPGA_MERGE_VALUES %3(s16), %7(s16), %10(s16), %46(s16), 16, 16, 16, 16
  
  bb.2.blockL192i0_192:
    successors: %bb.2(0x78e38e39), %bb.1(0x071c71c7)
  
    %3:anyregcls(s16) = HWTFPGA_EXTRACT %68(s64), 64, 0, 16
    %7:anyregcls(s16) = HWTFPGA_EXTRACT %68(s64), 64, 16, 16
    %10:anyregcls(s16) = HWTFPGA_EXTRACT %68(s64), 64, 32, 16
    %46:anyregcls(s16) = HWTFPGA_EXTRACT %68(s64), 64, 48, 16
    %13:anyregcls(s2) = HWTFPGA_CLOAD %2, 0, 2, 1 :: (volatile load (s2) from %ir.o_addr, addrspace 3)
    %15:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %13(s2), i2 0
    %17:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %13(s2), i2 1
    %19:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %13(s2), i2 -2
    %22:anyregcls(s16) = HWTFPGA_MUX %46(s16), %15(s1), %10(s16), %17(s1), %7(s16), %19(s1), %3(s16)
    HWTFPGA_CSTORE %22(s16), %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    %23:anyregcls(s2) = HWTFPGA_CLOAD %0, 0, 2, 1 :: (volatile load (s2) from %ir.i, addrspace 1)
    %24:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %23(s2), i2 0
    %25:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %23(s2), i2 1
    %26:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %23(s2), i2 -2
    %29:anyregcls(s16) = HWTFPGA_MUX %46(s16), %24(s1), %10(s16), %25(s1), %7(s16), %26(s1), %3(s16)
    %31:anyregcls(s16) = HWTFPGA_ADD %29(s16), i16 1
    dead %66:anyregcls(s16) = HWTFPGA_MUX %10(s16)
    %12:anyregcls(s16) = HWTFPGA_MUX %46(s16)
    %7:anyregcls(s16) = HWTFPGA_MUX %7(s16), %24(s1), %31(s16)
    %46:anyregcls(s16) = HWTFPGA_MUX %31(s16), %24(s1), %46(s16)
    %56:anyregcls(s1) = HWTFPGA_NOT %24(s1)
    %58:anyregcls(s1) = HWTFPGA_NOT %26(s1)
    %60:anyregcls(s1) = HWTFPGA_AND %56(s1), %58(s1)
    %35:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %23(s2), i2 -1
    %44:anyregcls(s16) = HWTFPGA_MUX %10(s16), %35(s1), %31(s16)
    %65:anyregcls(s1) = HWTFPGA_AND %35(s1), %60(s1)
    %3:anyregcls(s16) = HWTFPGA_MUX %31(s16), %65(s1), %3(s16)
    %67:anyregcls(s64) = HWTFPGA_MERGE_VALUES %3(s16), %7(s16), %12(s16), %44(s16), 16, 16, 16, 16
    %68:anyregcls(s64) = HWTFPGA_MERGE_VALUES %3(s16), %7(s16), %10(s16), %46(s16), 16, 16, 16, 16
    HWTFPGA_BRCOND %60(s1), %bb.1
    HWTFPGA_BR %bb.2

...
