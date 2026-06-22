--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @"BitWidthReductionCmp2Values.hwImpl.<locals>.mainThread"(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.io !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %bb0, %loopHeader
    %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
    %0 = call i15 @hwtHls.bitRangeGet.i16.i5.i15.1(i16 %i_read2, i5 1) #1
    %1 = icmp eq i16 %i_read2, 10
    %2 = xor i1 %1, true
    %3 = icmp ne i15 %0, 5
    %4 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %2, i1 %1, i1 %2) #1
    %.sink34 = select i1 %3, i3 -4, i3 %4
    %5 = call i2 @hwtHls.bitRangeGet.i3.i3.i2.1(i3 %.sink34, i3 1) #1
    %6 = call i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3 %.sink34, i3 0) #1
    %7 = call i16 @hwtHls.bitConcat.i1.i1.i2.i12(i1 %6, i1 %3, i2 %5, i12 1) #1
    store volatile i16 %7, ptr addrspace(2) %o, align 2
    br label %loopHeader
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i15 @hwtHls.bitRangeGet.i16.i5.i15.1(i16, i5) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i3 @hwtHls.bitConcat.i1.i1.i1(i1, i1, i1) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i1 @hwtHls.bitRangeGet.i3.i3.i1.0(i3, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i2 @hwtHls.bitRangeGet.i3.i3.i2.1(i3, i3) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i1.i1.i2.i12(i1, i1, i2, i12) #0
  
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
  - { id: 4, class: _, preferred-register: '', flags: [  ] }
  - { id: 5, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 6, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 7, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 8, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 9, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 10, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 11, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 12, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 13, class: anyregbank, preferred-register: '', flags: [  ] }
  - { id: 14, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 15, class: _, preferred-register: '', flags: [  ] }
  - { id: 16, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 17, class: _, preferred-register: '', flags: [  ] }
  - { id: 18, class: anyregcls, preferred-register: '', flags: [  ] }
  - { id: 19, class: anyregcls, preferred-register: '', flags: [  ] }
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
  
  bb.1.loopHeader:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 16, 1 :: (volatile load (s16) from %ir.i, addrspace 1)
    %3:anyregcls(s15) = HWTFPGA_EXTRACT %2(s16), 16, 1, 15
    %6:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s16), i16 10
    %8:anyregcls(s1) = HWTFPGA_NOT %6(s1)
    %10:anyregcls(s1) = HWTFPGA_ICMP intpred(ne), %3(s15), i15 5
    %11:anyregcls(s3) = HWTFPGA_MERGE_VALUES %8(s1), %6(s1), %8(s1), 1, 1, 1
    %12:anyregcls(s3) = HWTFPGA_MUX i3 -4, %10(s1), %11(s3)
    %14:anyregcls(s2) = HWTFPGA_EXTRACT %12(s3), 3, 1, 2
    %16:anyregcls(s1) = HWTFPGA_EXTRACT %12(s3), 3, 0, 1
    %18:anyregcls(s16) = HWTFPGA_MERGE_VALUES %16(s1), %10(s1), %14(s2), i12 1, 1, 1, 2, 12
    HWTFPGA_CSTORE %18(s16), %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1
...
