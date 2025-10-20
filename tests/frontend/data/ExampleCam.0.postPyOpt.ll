define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL52i0_52

blockL52i0_52:                                    ; preds = %block0
  br label %blockL52i0_56

blockL52i0_56:                                    ; preds = %blockL52i0_52
  %k0_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k0_key, align 2
  %k0_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k0_vld, align 1
  br label %blockL52i1_52

blockL52i1_52:                                    ; preds = %blockL52i0_56
  br label %blockL52i1_56

blockL52i1_56:                                    ; preds = %blockL52i1_52
  %k1_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k1_key, align 2
  %k1_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k1_vld, align 1
  br label %blockL52i2_52

blockL52i2_52:                                    ; preds = %blockL52i1_56
  br label %blockL52i2_56

blockL52i2_56:                                    ; preds = %blockL52i2_52
  %k2_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k2_key, align 2
  %k2_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k2_vld, align 1
  br label %blockL52i3_52

blockL52i3_52:                                    ; preds = %blockL52i2_56
  br label %blockL52i3_56

blockL52i3_56:                                    ; preds = %blockL52i3_52
  %k3_key = alloca i16, align 2, !hwtHls.tmp.alloca !6
  store i16 undef, ptr %k3_key, align 2
  %k3_vld = alloca i1, align 1, !hwtHls.tmp.alloca !6
  store i1 undef, ptr %k3_vld, align 1
  br label %blockL52i4_52

blockL52i4_52:                                    ; preds = %blockL52i3_56
  br label %block104

block104:                                         ; preds = %blockL52i4_52
  br label %blockL114i0_114

blockL114i0_114:                                  ; preds = %block104
  br label %ExampleCam.updateThread.rstLoop

ExampleCam.updateThread.rstLoop:                  ; preds = %blockL114i0_114
  store i1 false, ptr %k0_vld, align 1
  br label %blockL114i1_114

blockL114i1_114:                                  ; preds = %ExampleCam.updateThread.rstLoop
  br label %ExampleCam.updateThread.rstLoop1

ExampleCam.updateThread.rstLoop1:                 ; preds = %blockL114i1_114
  store i1 false, ptr %k1_vld, align 1
  br label %blockL114i2_114

blockL114i2_114:                                  ; preds = %ExampleCam.updateThread.rstLoop1
  br label %ExampleCam.updateThread.rstLoop2

ExampleCam.updateThread.rstLoop2:                 ; preds = %blockL114i2_114
  store i1 false, ptr %k2_vld, align 1
  br label %blockL114i3_114

blockL114i3_114:                                  ; preds = %ExampleCam.updateThread.rstLoop2
  br label %ExampleCam.updateThread.rstLoop3

ExampleCam.updateThread.rstLoop3:                 ; preds = %blockL114i3_114
  store i1 false, ptr %k3_vld, align 1
  br label %blockL114i4_114

blockL114i4_114:                                  ; preds = %ExampleCam.updateThread.rstLoop3
  br label %block178

block178:                                         ; preds = %blockL114i4_114
  br label %blockL192i0_192

blockL192i0_192:                                  ; preds = %blockL192i0_534, %block178
  br label %blockL192i0_L214i0_214

blockL192i0_L214i0_214:                           ; preds = %blockL192i0_192
  br label %ExampleCam.updateThread.keyExportLoop

ExampleCam.updateThread.keyExportLoop:            ; preds = %blockL192i0_L214i0_214
  %k0_vld4 = load i1, ptr %k0_vld, align 1
  %k0_key5 = load i16, ptr %k0_key, align 2
  %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key5, i1 %k0_vld4) #1
  store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
  br label %blockL192i0_L214i1_214

blockL192i0_L214i1_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop
  br label %ExampleCam.updateThread.keyExportLoop1

ExampleCam.updateThread.keyExportLoop1:           ; preds = %blockL192i0_L214i1_214
  %k1_vld2 = load i1, ptr %k1_vld, align 1
  %k1_key3 = load i16, ptr %k1_key, align 2
  %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key3, i1 %k1_vld2) #1
  store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
  br label %blockL192i0_L214i2_214

blockL192i0_L214i2_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop1
  br label %ExampleCam.updateThread.keyExportLoop2

ExampleCam.updateThread.keyExportLoop2:           ; preds = %blockL192i0_L214i2_214
  %k2_vld3 = load i1, ptr %k2_vld, align 1
  %k2_key4 = load i16, ptr %k2_key, align 2
  %2 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k2_key4, i1 %k2_vld3) #1
  store volatile i17 %2, ptr addrspace(3) %keyForMatchThread_2, align 4
  br label %blockL192i0_L214i3_214

blockL192i0_L214i3_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop2
  br label %ExampleCam.updateThread.keyExportLoop3

ExampleCam.updateThread.keyExportLoop3:           ; preds = %blockL192i0_L214i3_214
  %k3_vld4 = load i1, ptr %k3_vld, align 1
  %k3_key5 = load i16, ptr %k3_key, align 2
  %3 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k3_key5, i1 %k3_vld4) #1
  store volatile i17 %3, ptr addrspace(4) %keyForMatchThread_3, align 4
  br label %blockL192i0_L214i4_214

blockL192i0_L214i4_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop3
  br label %ExampleCam.updateThread.keyUpdate

ExampleCam.updateThread.keyUpdate:                ; preds = %blockL192i0_L214i4_214
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
  switch i2 %write_read_addr3, label %ExampleCam.updateThread.keyUpdate_518_setSwEnd [
    i2 0, label %ExampleCam.updateThread.keyUpdate_518_c0
    i2 1, label %ExampleCam.updateThread.keyUpdate_518_c1
    i2 -2, label %ExampleCam.updateThread.keyUpdate_518_c2
    i2 -1, label %ExampleCam.updateThread.keyUpdate_518_c3
  ]

ExampleCam.updateThread.keyUpdate_518_setSwEnd:   ; preds = %ExampleCam.updateThread.keyUpdate_518_c3, %ExampleCam.updateThread.keyUpdate_518_c2, %ExampleCam.updateThread.keyUpdate_518_c1, %ExampleCam.updateThread.keyUpdate_518_c0, %ExampleCam.updateThread.keyUpdate
  br label %blockL192i0_534

ExampleCam.updateThread.keyUpdate_518_c0:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key6 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key6, ptr %k0_key, align 2
  %newKey_vld7 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld7, ptr %k0_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c1:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key8 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key8, ptr %k1_key, align 2
  %newKey_vld9 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld9, ptr %k1_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c2:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key10 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key10, ptr %k2_key, align 2
  %newKey_vld11 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld11, ptr %k2_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c3:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key12 = load i16, ptr %newKey_key, align 2
  store i16 %newKey_key12, ptr %k3_key, align 2
  %newKey_vld13 = load i1, ptr %newKey_vld, align 1
  store i1 %newKey_vld13, ptr %k3_vld, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

blockL192i0_534:                                  ; preds = %ExampleCam.updateThread.keyUpdate_518_setSwEnd
  br label %blockL192i0_192
}
define void @ExampleCam.matchThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %match, ptr addrspace(6) %out) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL14i0_14

blockL14i0_14:                                    ; preds = %blockL14i0_370, %block0
  %match_read = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %match_read, align 2
  %m = alloca i16, align 2, !hwtHls.tmp.alloca !7
  store i16 undef, ptr %m, align 2
  %match_read1 = load volatile i16, ptr addrspace(5) %match, align 2
  store i16 %match_read1, ptr %match_read, align 2
  %match_read2 = load i16, ptr %match_read, align 2
  store i16 %match_read2, ptr %m, align 2
  br label %blockL14i0_L96i0_96

blockL14i0_L96i0_96:                              ; preds = %blockL14i0_14
  br label %blockL14i0_L96i0_100

blockL14i0_L96i0_100:                             ; preds = %blockL14i0_L96i0_96
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
  br label %blockL14i0_L96i1_96

blockL14i0_L96i1_96:                              ; preds = %blockL14i0_L96i0_100
  br label %blockL14i0_L96i1_100

blockL14i0_L96i1_100:                             ; preds = %blockL14i0_L96i1_96
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
  br label %blockL14i0_L96i2_96

blockL14i0_L96i2_96:                              ; preds = %blockL14i0_L96i1_100
  br label %blockL14i0_L96i2_100

blockL14i0_L96i2_100:                             ; preds = %blockL14i0_L96i2_96
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
  br label %blockL14i0_L96i3_96

blockL14i0_L96i3_96:                              ; preds = %blockL14i0_L96i2_100
  br label %blockL14i0_L96i3_100

blockL14i0_L96i3_100:                             ; preds = %blockL14i0_L96i3_96
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
  br label %blockL14i0_L96i4_96

blockL14i0_L96i4_96:                              ; preds = %blockL14i0_L96i3_100
  br label %blockL14i0_270

blockL14i0_270:                                   ; preds = %blockL14i0_L96i4_96
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
  br label %blockL14i0_370

blockL14i0_370:                                   ; preds = %blockL14i0_270
  br label %blockL14i0_14
}
