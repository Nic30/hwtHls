--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @"BitWidthReductionCmp2Values.hwImpl.<locals>.mainThread"(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %bb0, %loopHeader
    %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
    %0 = icmp eq i16 %i_read2, 10
    %1 = xor i1 %0, true
    %2 = icmp eq i16 %i_read2, 11
    %3 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %1, i1 %0, i1 %1) #1
    %.sink34 = select i1 %2, i3 -4, i3 %3
    %4 = call i16 @hwtHls.bitConcat.i1.i3.i12(i1 %2, i3 %.sink34, i12 1) #1
    store volatile i16 %4, ptr addrspace(2) %o, align 2
    br label %loopHeader
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i3 @hwtHls.bitConcat.i1.i1.i1(i1, i1, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i1.i3.i12(i1, i3, i12) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 16, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 16, ptr null, i64 1}

...
---
name:            'BitWidthReductionCmp2Values.hwImpl.<locals>.mainThread'
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
  - { id: 3, class: anyregbank, preferred-register: '' }
  - { id: 4, class: anyregcls, preferred-register: '' }
  - { id: 5, class: anyregbank, preferred-register: '' }
  - { id: 6, class: anyregcls, preferred-register: '' }
  - { id: 7, class: anyregbank, preferred-register: '' }
  - { id: 8, class: anyregcls, preferred-register: '' }
  - { id: 9, class: anyregcls, preferred-register: '' }
  - { id: 10, class: anyregcls, preferred-register: '' }
  - { id: 11, class: anyregbank, preferred-register: '' }
  - { id: 12, class: anyregcls, preferred-register: '' }
  - { id: 13, class: anyregcls, preferred-register: '' }
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
  
  bb.1.loopHeader:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 16, 1 :: (volatile load (s16) from %ir.i, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s16), i16 10
    %6:anyregcls(s1) = HWTFPGA_NOT %4(s1)
    %8:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s16), i16 11
    %9:anyregcls(s3) = HWTFPGA_MERGE_VALUES %6(s1), %4(s1), %6(s1), 1, 1, 1
    %10:anyregcls(s3) = HWTFPGA_MUX i3 -4, %8(s1), %9(s3)
    %12:anyregcls(s16) = HWTFPGA_MERGE_VALUES %8(s1), %10(s3), i12 1, 1, 3, 12
    HWTFPGA_CSTORE %12(s16), %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

...
