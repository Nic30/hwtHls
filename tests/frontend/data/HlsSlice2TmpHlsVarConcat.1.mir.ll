--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsSlice2TmpHlsVarConcat.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b) !hwtHls.io !0 {
  bb0:
    br label %blockL24i0_24
  
  blockL24i0_24:                                    ; preds = %bb0, %blockL24i0_24
    %a_read1 = load volatile i16, ptr addrspace(1) %a, align 2
    %0 = call i32 @hwtHls.bitConcat.i16.i16(i16 %a_read1, i16 16) #1
    store volatile i32 %0, ptr addrspace(2) %b, align 4
    br label %blockL24i0_24
  }
  
  ; Function Attrs: nofree nounwind speculatable willreturn
  declare i32 @hwtHls.bitConcat.i16.i16(i16, i16) #0
  
  attributes #0 = { nofree nounwind speculatable willreturn }
  attributes #1 = { memory(none) }
  
  !0 = distinct !{!1, !2}
  !1 = !{!"IN", i64 0, i64 16, i64 0, ptr null, i64 0}
  !2 = !{!"OUT", i64 0, i64 0, i64 32, ptr null, i64 1}
...
---
name:            HlsSlice2TmpHlsVarConcat.mainThread
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
  
  bb.1.blockL24i0_24:
    successors: %bb.1(0x80000000)
  
    %2:anyregcls(s16) = HWTFPGA_CLOAD %0, 0, 16, 1 :: (volatile load (s16) from %ir.a, addrspace 1)
    %3:anyregcls(s32) = HWTFPGA_MERGE_VALUES %2(s16), i16 16, 16, 16
    HWTFPGA_CSTORE %3(s32), %1, 0, 32, 1 :: (volatile store (s32) into %ir.b, addrspace 2)
    HWTFPGA_BR %bb.1
...
