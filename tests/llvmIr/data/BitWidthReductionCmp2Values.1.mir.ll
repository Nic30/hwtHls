--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @"BitWidthReductionCmp2Values.hwImpl.<locals>.mainThread"(ptr addrspace(1) %i, ptr addrspace(2) %o) !hwtHls.param_addr_width !0 {
  bb0:
    br label %loopHeader
  
  loopHeader:                                       ; preds = %loopHeader, %bb0
    %i_read2 = load volatile i16, ptr addrspace(1) %i, align 2
    %switch.selectcmp = icmp eq i16 %i_read2, 11
    %0 = xor i1 %switch.selectcmp, true
    %switch.selectcmp3 = icmp eq i16 %i_read2, 10
    %1 = call i4 @hwtHls.bitConcat.i1.i1.i2(i1 %switch.selectcmp, i1 %0, i2 -2) #1
    %switch.select45 = select i1 %switch.selectcmp3, i4 4, i4 %1
    %2 = call i16 @hwtHls.bitConcat.i4.i12(i4 %switch.select45, i12 1) #1
    store volatile i16 %2, ptr addrspace(2) %o, align 2
    br label %loopHeader
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i4 @hwtHls.bitConcat.i1.i1.i2(i1, i1, i2) #0
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i16 @hwtHls.bitConcat.i4.i12(i4, i12) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!0, !1}
  !1 = !{i32 0, i32 0}

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
  - { id: 11, class: anyregcls, preferred-register: '' }
  - { id: 12, class: anyregbank, preferred-register: '' }
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
  
  bb.1.loopHeader:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 16, 1 :: (volatile load (s16) from %ir.i, addrspace 1)
    %4:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s16), i16 11
    %6:anyregcls(s1) = HWTFPGA_NOT %4(s1)
    %8:anyregcls(s1) = HWTFPGA_ICMP intpred(eq), %2(s16), i16 10
    %9:anyregcls(s4) = HWTFPGA_MERGE_VALUES %4(s1), %6(s1), i2 -2, 1, 1, 2
    %11:anyregcls(s4) = HWTFPGA_MUX i4 4, %8(s1), %9(s4)
    %13:anyregcls(s16) = HWTFPGA_MERGE_VALUES %11(s4), i12 1, 4, 12
    HWTFPGA_CSTORE %13(s16), %1, 0, 16, 1 :: (volatile store (s16) into %ir.o, addrspace 2)
    HWTFPGA_BR %bb.1

...
