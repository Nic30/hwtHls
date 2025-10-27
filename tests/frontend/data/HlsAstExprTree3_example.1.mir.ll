--- |
  ; ModuleID = 'hwtHlsModule'
  source_filename = "hwtHlsModule"
  target datalayout = "e-m:e-i8:8-i16:16-i32:32-i64:64-i128:128-i256:256-i512:512-i1024:1024-i2048:2048-i4096:4096-n8:16:32:64-S128-v16:16-v24:32-v32:32-v48:64-v96:128-v192:256-v256:256-v512:512-v1024:1024"
  
  define void @HlsAstExprTree3_example.mainThread(ptr addrspace(1) %a, ptr addrspace(2) %b, ptr addrspace(3) %c, ptr addrspace(4) %d, ptr addrspace(5) %f1, ptr addrspace(6) %f2, ptr addrspace(7) %f3, ptr addrspace(8) %w, ptr addrspace(9) %x, ptr addrspace(10) %y, ptr addrspace(11) %z) !hwtHls.io !0 {
  bb0:
    br label %blockL74i0_74
  
  blockL74i0_74:                                    ; preds = %bb0, %blockL74i0_74
    %a_read1 = load volatile i32, ptr addrspace(1) %a, align 4
    %b_read1 = load volatile i32, ptr addrspace(2) %b, align 4
    %c_read1 = load volatile i32, ptr addrspace(3) %c, align 4
    %d_read1 = load volatile i32, ptr addrspace(4) %d, align 4
    %x_read2 = load volatile i32, ptr addrspace(9) %x, align 4
    %y_read2 = load volatile i32, ptr addrspace(10) %y, align 4
    %z_read2 = load volatile i32, ptr addrspace(11) %z, align 4
    %w_read2 = load volatile i32, ptr addrspace(8) %w, align 4
    %0 = add i32 %b_read1, %a_read1
    %1 = add i32 %0, %c_read1
    %f18 = mul i32 %1, %d_read1
    %xy9 = add i32 %y_read2, %x_read2
    %f210 = mul i32 %xy9, %z_read2
    %f311 = mul i32 %w_read2, %xy9
    store volatile i32 %f18, ptr addrspace(5) %f1, align 4
    store volatile i32 %f210, ptr addrspace(6) %f2, align 4
    store volatile i32 %f311, ptr addrspace(7) %f3, align 4
    br label %blockL74i0_74
  }
  
  !0 = distinct !{!1, !2, !3, !4, !5, !6, !7, !8, !9, !10, !11}
  !1 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 0}
  !2 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 1}
  !3 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 2}
  !4 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 3}
  !5 = !{!"OUT", i64 0, i64 0, i64 32, ptr null, i64 4}
  !6 = !{!"OUT", i64 0, i64 0, i64 32, ptr null, i64 5}
  !7 = !{!"OUT", i64 0, i64 0, i64 32, ptr null, i64 6}
  !8 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 7}
  !9 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 8}
  !10 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 9}
  !11 = !{!"IN", i64 0, i64 32, i64 0, ptr null, i64 10}

...
---
name:            HlsAstExprTree3_example.mainThread
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
  - { id: 14, class: anyregcls, preferred-register: '' }
  - { id: 15, class: anyregcls, preferred-register: '' }
  - { id: 16, class: anyregcls, preferred-register: '' }
  - { id: 17, class: anyregcls, preferred-register: '' }
  - { id: 18, class: anyregcls, preferred-register: '' }
  - { id: 19, class: anyregcls, preferred-register: '' }
  - { id: 20, class: anyregcls, preferred-register: '' }
  - { id: 21, class: anyregcls, preferred-register: '' }
  - { id: 22, class: anyregcls, preferred-register: '' }
  - { id: 23, class: anyregcls, preferred-register: '' }
  - { id: 24, class: anyregcls, preferred-register: '' }
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
    %3:anyregcls = HWTFPGA_ARG_GET 3
    %4:anyregcls = HWTFPGA_ARG_GET 4
    %5:anyregcls = HWTFPGA_ARG_GET 5
    %6:anyregcls = HWTFPGA_ARG_GET 6
    %7:anyregcls = HWTFPGA_ARG_GET 7
    %8:anyregcls = HWTFPGA_ARG_GET 8
    %9:anyregcls = HWTFPGA_ARG_GET 9
    %10:anyregcls = HWTFPGA_ARG_GET 10
  
  bb.1.blockL74i0_74:
    successors: %bb.1(0x80000000)
  
    %11:anyregcls(s32) = HWTFPGA_CLOAD %0, 0, 32, 1 :: (volatile load (s32) from %ir.a, addrspace 1)
    %12:anyregcls(s32) = HWTFPGA_CLOAD %1, 0, 32, 1 :: (volatile load (s32) from %ir.b, addrspace 2)
    %13:anyregcls(s32) = HWTFPGA_CLOAD %2, 0, 32, 1 :: (volatile load (s32) from %ir.c, addrspace 3)
    %14:anyregcls(s32) = HWTFPGA_CLOAD %3, 0, 32, 1 :: (volatile load (s32) from %ir.d, addrspace 4)
    %15:anyregcls(s32) = HWTFPGA_CLOAD %8, 0, 32, 1 :: (volatile load (s32) from %ir.x, addrspace 9)
    %16:anyregcls(s32) = HWTFPGA_CLOAD %9, 0, 32, 1 :: (volatile load (s32) from %ir.y, addrspace 10)
    %17:anyregcls(s32) = HWTFPGA_CLOAD %10, 0, 32, 1 :: (volatile load (s32) from %ir.z, addrspace 11)
    %18:anyregcls(s32) = HWTFPGA_CLOAD %7, 0, 32, 1 :: (volatile load (s32) from %ir.w, addrspace 8)
    %19:anyregcls(s32) = HWTFPGA_ADD %12(s32), %11(s32)
    %20:anyregcls(s32) = HWTFPGA_ADD %19(s32), %13(s32)
    %21:anyregcls(s32) = HWTFPGA_MUL %20(s32), %14(s32)
    %22:anyregcls(s32) = HWTFPGA_ADD %16(s32), %15(s32)
    %23:anyregcls(s32) = HWTFPGA_MUL %22(s32), %17(s32)
    %24:anyregcls(s32) = HWTFPGA_MUL %18(s32), %22(s32)
    HWTFPGA_CSTORE %21(s32), %4, 0, 32, 1 :: (volatile store (s32) into %ir.f1, addrspace 5)
    HWTFPGA_CSTORE %23(s32), %5, 0, 32, 1 :: (volatile store (s32) into %ir.f2, addrspace 6)
    HWTFPGA_CSTORE %24(s32), %6, 0, 32, 1 :: (volatile store (s32) into %ir.f3, addrspace 7)
    HWTFPGA_BR %bb.1

...
