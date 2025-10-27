define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL54i0_54

blockL54i0_54:                                    ; preds = %block0
  br label %blockL54i0_58

blockL54i0_58:                                    ; preds = %blockL54i0_54
  %k0_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k0_key, align 2
  %k0_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k0_vld, align 1
  br label %blockL54i1_54

blockL54i1_54:                                    ; preds = %blockL54i0_58
  br label %blockL54i1_58

blockL54i1_58:                                    ; preds = %blockL54i1_54
  %k1_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k1_key, align 2
  %k1_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k1_vld, align 1
  br label %blockL54i2_54

blockL54i2_54:                                    ; preds = %blockL54i1_58
  br label %blockL54i2_58

blockL54i2_58:                                    ; preds = %blockL54i2_54
  %k2_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k2_key, align 2
  %k2_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k2_vld, align 1
  br label %blockL54i3_54

blockL54i3_54:                                    ; preds = %blockL54i2_58
  br label %blockL54i3_58

blockL54i3_58:                                    ; preds = %blockL54i3_54
  %k3_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k3_key, align 2
  %k3_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k3_vld, align 1
  br label %blockL54i4_54

blockL54i4_54:                                    ; preds = %blockL54i3_58
  br label %block106

block106:                                         ; preds = %blockL54i4_54
  br label %blockL118i0_118

blockL118i0_118:                                  ; preds = %block106
  br label %ExampleCam.updateThread.rstLoop

ExampleCam.updateThread.rstLoop:                  ; preds = %blockL118i0_118
  store i1 false, ptr %k0_vld, align 1
  br label %blockL118i1_118

blockL118i1_118:                                  ; preds = %ExampleCam.updateThread.rstLoop
  br label %ExampleCam.updateThread.rstLoop1

ExampleCam.updateThread.rstLoop1:                 ; preds = %blockL118i1_118
  store i1 false, ptr %k1_vld, align 1
  br label %blockL118i2_118

blockL118i2_118:                                  ; preds = %ExampleCam.updateThread.rstLoop1
  br label %ExampleCam.updateThread.rstLoop2

ExampleCam.updateThread.rstLoop2:                 ; preds = %blockL118i2_118
  store i1 false, ptr %k2_vld, align 1
  br label %blockL118i3_118

blockL118i3_118:                                  ; preds = %ExampleCam.updateThread.rstLoop2
  br label %ExampleCam.updateThread.rstLoop3

ExampleCam.updateThread.rstLoop3:                 ; preds = %blockL118i3_118
  store i1 false, ptr %k3_vld, align 1
  br label %blockL118i4_118

blockL118i4_118:                                  ; preds = %ExampleCam.updateThread.rstLoop3
  br label %block184

block184:                                         ; preds = %blockL118i4_118
  br label %blockL210i0_210

blockL210i0_210:                                  ; preds = %blockL210i0_560, %block184
  br label %blockL210i0_L232i0_232

blockL210i0_L232i0_232:                           ; preds = %blockL210i0_210
  br label %ExampleCam.updateThread.keyExportLoop

ExampleCam.updateThread.keyExportLoop:            ; preds = %blockL210i0_L232i0_232
  %k0_vld4 = load i1, ptr %k0_vld, align 1
  %k0_key5 = load i16, ptr %k0_key, align 2
  %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key5, i1 %k0_vld4) #1
  store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
  br label %blockL210i0_L232i1_232

blockL210i0_L232i1_232:                           ; preds = %ExampleCam.updateThread.keyExportLoop
  br label %ExampleCam.updateThread.keyExportLoop1

ExampleCam.updateThread.keyExportLoop1:           ; preds = %blockL210i0_L232i1_232
  %k1_vld2 = load i1, ptr %k1_vld, align 1
  %k1_key3 = load i16, ptr %k1_key, align 2
  %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key3, i1 %k1_vld2) #1
  store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
  br label %blockL210i0_L232i2_232

blockL210i0_L232i2_232:                           ; preds = %ExampleCam.updateThread.keyExportLoop1
  br label %ExampleCam.updateThread.keyExportLoop2

ExampleCam.updateThread.keyExportLoop2:           ; preds = %blockL210i0_L232i2_232
  %k2_vld3 = load i1, ptr %k2_vld, align 1
  %k2_key4 = load i16, ptr %k2_key, align 2
  %2 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k2_key4, i1 %k2_vld3) #1
  store volatile i17 %2, ptr addrspace(3) %keyForMatchThread_2, align 4
  br label %blockL210i0_L232i3_232

blockL210i0_L232i3_232:                           ; preds = %ExampleCam.updateThread.keyExportLoop2
  br label %ExampleCam.updateThread.keyExportLoop3

ExampleCam.updateThread.keyExportLoop3:           ; preds = %blockL210i0_L232i3_232
  %k3_vld4 = load i1, ptr %k3_vld, align 1
  %k3_key5 = load i16, ptr %k3_key, align 2
  %3 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k3_key5, i1 %k3_vld4) #1
  store volatile i17 %3, ptr addrspace(4) %keyForMatchThread_3, align 4
  br label %blockL210i0_L232i4_232

blockL210i0_L232i4_232:                           ; preds = %ExampleCam.updateThread.keyExportLoop3
  br label %ExampleCam.updateThread.keyUpdate

ExampleCam.updateThread.keyUpdate:                ; preds = %blockL210i0_L232i4_232
  %write_read_addr = alloca i2, align 1, !hwtHls.tmp.alloca !6
  store i2 undef, ptr %write_read_addr, align 1
  %write_read_data = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %write_read_data, align 2
  %write_read_vld_flag = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %write_read_vld_flag, align 1
  %write_read = alloca i19, align 4, !hwtHls.tmp.alloca !6
  store i19 undef, ptr %write_read, align 4
  %w_addr = alloca i2, align 1, !hwtHls.tmp.alloca !6
  store i2 undef, ptr %w_addr, align 1
  %w_data = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %w_data, align 2
  %w_vld_flag = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %w_vld_flag, align 1
  %write_read1 = load volatile i19, ptr addrspace(5) %write, align 4
  store i19 %write_read1, ptr %write_read, align 4
  %write_read2 = load i19, ptr %write_read, align 4
  %write_read_vld_flag5 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %write_read2, i6 18) #1
  %write_read_data4 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.2(i19 %write_read2, i6 2) #1
  %write_read_addr3 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read2, i6 0) #1
  store i2 %write_read_addr3, ptr %w_addr, align 1
  store i16 %write_read_data4, ptr %w_data, align 2
  store i1 %write_read_vld_flag5, ptr %w_vld_flag, align 1
  %newKey_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %newKey_key, align 2
  %newKey_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %newKey_vld, align 1
  store i16 undef, ptr %newKey_key, align 2
  store i1 undef, ptr %newKey_vld, align 1
  store i1 %write_read_vld_flag5, ptr %newKey_vld, align 1
  store i16 %write_read_data4, ptr %newKey_key, align 2
  switch i2 %write_read_addr3, label %ExampleCam.updateThread.keyUpdate_534_setSwEnd [
    i2 0, label %ExampleCam.updateThread.keyUpdate_534_c0
    i2 1, label %ExampleCam.updateThread.keyUpdate_534_c1
    i2 -2, label %ExampleCam.updateThread.keyUpdate_534_c2
    i2 -1, label %ExampleCam.updateThread.keyUpdate_534_c3
  ]

ExampleCam.updateThread.keyUpdate_534_setSwEnd:   ; preds = %ExampleCam.updateThread.keyUpdate_534_c3, %ExampleCam.updateThread.keyUpdate_534_c2, %ExampleCam.updateThread.keyUpdate_534_c1, %ExampleCam.updateThread.keyUpdate_534_c0, %ExampleCam.updateThread.keyUpdate
  br label %blockL210i0_560

ExampleCam.updateThread.keyUpdate_534_c0:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key6 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key6, ptr %k0_key, align 2
  %newKey_vld7 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld7, ptr %k0_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_534_setSwEnd

ExampleCam.updateThread.keyUpdate_534_c1:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key8 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key8, ptr %k1_key, align 2
  %newKey_vld9 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld9, ptr %k1_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_534_setSwEnd

ExampleCam.updateThread.keyUpdate_534_c2:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key10 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key10, ptr %k2_key, align 2
  %newKey_vld11 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld11, ptr %k2_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_534_setSwEnd

ExampleCam.updateThread.keyUpdate_534_c3:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key12 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key12, ptr %k3_key, align 2
  %newKey_vld13 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld13, ptr %k3_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_534_setSwEnd

blockL210i0_560:                                  ; preds = %ExampleCam.updateThread.keyUpdate_534_setSwEnd
  br label %blockL210i0_210
}
define void @ExampleCam.matchThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %match, ptr addrspace(6) %out) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL24i0_24

blockL24i0_24:                                    ; preds = %blockL24i0_394, %block0
  %match_read = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %match_read, align 2
  %m = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %m, align 2
  %match_read1 = load volatile i16, ptr addrspace(5) %match, align 2
  store i16 %match_read1, ptr %match_read, align 2
  %match_read2 = load i16, ptr %match_read, align 2
  store i16 %match_read2, ptr %m, align 2
  br label %blockL24i0_L106i0_106

blockL24i0_L106i0_106:                            ; preds = %blockL24i0_24
  br label %blockL24i0_L106i0_110

blockL24i0_L106i0_110:                            ; preds = %blockL24i0_L106i0_106
  %keyForMatchThread_0_read_key = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %keyForMatchThread_0_read_key, align 2
  %keyForMatchThread_0_read_vld = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %keyForMatchThread_0_read_vld, align 1
  %keyForMatchThread_0_read = alloca i17, align 4, !hwtHls.tmp.alloca !7
  store i17 undef, ptr %keyForMatchThread_0_read, align 4
  %_k_key = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %_k_key, align 2
  %_k_vld = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %_k_vld, align 1
  %keyForMatchThread_0_read1 = load volatile i17, ptr addrspace(1) %keyForMatchThread_0, align 4
  store i17 %keyForMatchThread_0_read1, ptr %keyForMatchThread_0_read, align 4
  %keyForMatchThread_0_read2 = load i17, ptr %keyForMatchThread_0_read, align 4
  %keyForMatchThread_0_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_0_read2, i6 16) #1
  %keyForMatchThread_0_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_0_read2, i6 0) #1
  store i16 %keyForMatchThread_0_read_key3, ptr %_k_key, align 2
  store i1 %keyForMatchThread_0_read_vld4, ptr %_k_vld, align 1
  br label %blockL24i0_L106i1_106

blockL24i0_L106i1_106:                            ; preds = %blockL24i0_L106i0_110
  br label %blockL24i0_L106i1_110

blockL24i0_L106i1_110:                            ; preds = %blockL24i0_L106i1_106
  %keyForMatchThread_1_read_key = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %keyForMatchThread_1_read_key, align 2
  %keyForMatchThread_1_read_vld = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %keyForMatchThread_1_read_vld, align 1
  %keyForMatchThread_1_read = alloca i17, align 4, !hwtHls.tmp.alloca !7
  store i17 undef, ptr %keyForMatchThread_1_read, align 4
  %_k_key5 = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %_k_key5, align 2
  %_k_vld6 = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %_k_vld6, align 1
  %keyForMatchThread_1_read1 = load volatile i17, ptr addrspace(2) %keyForMatchThread_1, align 4
  store i17 %keyForMatchThread_1_read1, ptr %keyForMatchThread_1_read, align 4
  %keyForMatchThread_1_read2 = load i17, ptr %keyForMatchThread_1_read, align 4
  %keyForMatchThread_1_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_1_read2, i6 16) #1
  %keyForMatchThread_1_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_1_read2, i6 0) #1
  store i16 %keyForMatchThread_1_read_key3, ptr %_k_key5, align 2
  store i1 %keyForMatchThread_1_read_vld4, ptr %_k_vld6, align 1
  br label %blockL24i0_L106i2_106

blockL24i0_L106i2_106:                            ; preds = %blockL24i0_L106i1_110
  br label %blockL24i0_L106i2_110

blockL24i0_L106i2_110:                            ; preds = %blockL24i0_L106i2_106
  %keyForMatchThread_2_read_key = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %keyForMatchThread_2_read_key, align 2
  %keyForMatchThread_2_read_vld = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %keyForMatchThread_2_read_vld, align 1
  %keyForMatchThread_2_read = alloca i17, align 4, !hwtHls.tmp.alloca !7
  store i17 undef, ptr %keyForMatchThread_2_read, align 4
  %_k_key6 = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %_k_key6, align 2
  %_k_vld7 = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %_k_vld7, align 1
  %keyForMatchThread_2_read1 = load volatile i17, ptr addrspace(3) %keyForMatchThread_2, align 4
  store i17 %keyForMatchThread_2_read1, ptr %keyForMatchThread_2_read, align 4
  %keyForMatchThread_2_read2 = load i17, ptr %keyForMatchThread_2_read, align 4
  %keyForMatchThread_2_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_2_read2, i6 16) #1
  %keyForMatchThread_2_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_2_read2, i6 0) #1
  store i16 %keyForMatchThread_2_read_key3, ptr %_k_key6, align 2
  store i1 %keyForMatchThread_2_read_vld4, ptr %_k_vld7, align 1
  br label %blockL24i0_L106i3_106

blockL24i0_L106i3_106:                            ; preds = %blockL24i0_L106i2_110
  br label %blockL24i0_L106i3_110

blockL24i0_L106i3_110:                            ; preds = %blockL24i0_L106i3_106
  %keyForMatchThread_3_read_key = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %keyForMatchThread_3_read_key, align 2
  %keyForMatchThread_3_read_vld = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %keyForMatchThread_3_read_vld, align 1
  %keyForMatchThread_3_read = alloca i17, align 4, !hwtHls.tmp.alloca !7
  store i17 undef, ptr %keyForMatchThread_3_read, align 4
  %_k_key7 = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %_k_key7, align 2
  %_k_vld8 = alloca i1, align 1, !hwtHls.tmp.alloca !7
  store i1 undef, ptr %_k_vld8, align 1
  %keyForMatchThread_3_read1 = load volatile i17, ptr addrspace(4) %keyForMatchThread_3, align 4
  store i17 %keyForMatchThread_3_read1, ptr %keyForMatchThread_3_read, align 4
  %keyForMatchThread_3_read2 = load i17, ptr %keyForMatchThread_3_read, align 4
  %keyForMatchThread_3_read_vld4 = call i1 @hwtHls.bitRangeGet.i17.i6.i1.16(i17 %keyForMatchThread_3_read2, i6 16) #1
  %keyForMatchThread_3_read_key3 = call i16 @hwtHls.bitRangeGet.i17.i6.i16.0(i17 %keyForMatchThread_3_read2, i6 0) #1
  store i16 %keyForMatchThread_3_read_key3, ptr %_k_key7, align 2
  store i1 %keyForMatchThread_3_read_vld4, ptr %_k_vld8, align 1
  br label %blockL24i0_L106i4_106

blockL24i0_L106i4_106:                            ; preds = %blockL24i0_L106i3_110
  br label %blockL24i0_282

blockL24i0_282:                                   ; preds = %blockL24i0_L106i4_106
  %_k_vld5 = load i1, ptr %_k_vld8, align 1
  %0 = icmp eq i1 %_k_vld5, true
  %_k_key8 = load i16, ptr %_k_key7, align 2
  %m9 = load i16, ptr %m, align 2
  %1 = icmp eq i16 %_k_key8, %m9
  %2 = and i1 %0, %1
  %_k_vld10 = load i1, ptr %_k_vld7, align 1
  %3 = icmp eq i1 %_k_vld10, true
  %_k_key11 = load i16, ptr %_k_key6, align 2
  %4 = icmp eq i16 %_k_key11, %m9
  %5 = and i1 %3, %4
  %6 = call i2 @hwtHls.bitConcat.i1.i1(i1 %5, i1 %2) #1
  %_k_vld12 = load i1, ptr %_k_vld6, align 1
  %7 = icmp eq i1 %_k_vld12, true
  %_k_key13 = load i16, ptr %_k_key5, align 2
  %8 = icmp eq i16 %_k_key13, %m9
  %9 = and i1 %7, %8
  %10 = call i3 @hwtHls.bitConcat.i1.i2(i1 %9, i2 %6) #1
  %_k_vld14 = load i1, ptr %_k_vld, align 1
  %11 = icmp eq i1 %_k_vld14, true
  %_k_key15 = load i16, ptr %_k_key, align 2
  %12 = icmp eq i16 %_k_key15, %m9
  %13 = and i1 %11, %12
  %14 = call i4 @hwtHls.bitConcat.i1.i3(i1 %13, i3 %10) #1
  store volatile i4 %14, ptr addrspace(6) %out, align 1
  br label %blockL24i0_394

blockL24i0_394:                                   ; preds = %blockL24i0_282
  br label %blockL24i0_24
}
