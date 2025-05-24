define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %keyForMatchThread_2, ptr addrspace(4) %keyForMatchThread_3, ptr addrspace(5) %write) !hwtHls.param_addr_width !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %blockL52i0_52

blockL52i0_52:                                    ; preds = %block0
  br label %blockL52i0_56

blockL52i0_56:                                    ; preds = %blockL52i0_52
  %k0_key = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k0_key, align 2
  %k0_vld = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k0_vld, align 1
  %k0_key1 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k0_key1, align 2
  %k0_vld2 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k0_vld2, align 1
  br label %blockL52i1_52

blockL52i1_52:                                    ; preds = %blockL52i0_56
  br label %blockL52i1_56

blockL52i1_56:                                    ; preds = %blockL52i1_52
  %k1_key = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k1_key, align 2
  %k1_vld = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k1_vld, align 1
  %k1_key3 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k1_key3, align 2
  %k1_vld4 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k1_vld4, align 1
  br label %blockL52i2_52

blockL52i2_52:                                    ; preds = %blockL52i1_56
  br label %blockL52i2_56

blockL52i2_56:                                    ; preds = %blockL52i2_52
  %k2_key = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k2_key, align 2
  %k2_vld = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k2_vld, align 1
  %k2_key5 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k2_key5, align 2
  %k2_vld6 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k2_vld6, align 1
  br label %blockL52i3_52

blockL52i3_52:                                    ; preds = %blockL52i2_56
  br label %blockL52i3_56

blockL52i3_56:                                    ; preds = %blockL52i3_52
  %k3_key = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k3_key, align 2
  %k3_vld = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k3_vld, align 1
  %k3_key7 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %k3_key7, align 2
  %k3_vld8 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %k3_vld8, align 1
  br label %blockL52i4_52

blockL52i4_52:                                    ; preds = %blockL52i3_56
  br label %block104

block104:                                         ; preds = %blockL52i4_52
  br label %blockL114i0_114

blockL114i0_114:                                  ; preds = %block104
  br label %ExampleCam.updateThread.rstLoop

ExampleCam.updateThread.rstLoop:                  ; preds = %blockL114i0_114
  store i1 false, ptr %k0_vld2, align 1
  br label %blockL114i1_114

blockL114i1_114:                                  ; preds = %ExampleCam.updateThread.rstLoop
  br label %ExampleCam.updateThread.rstLoop9

ExampleCam.updateThread.rstLoop9:                 ; preds = %blockL114i1_114
  store i1 false, ptr %k1_vld4, align 1
  br label %blockL114i2_114

blockL114i2_114:                                  ; preds = %ExampleCam.updateThread.rstLoop9
  br label %ExampleCam.updateThread.rstLoop10

ExampleCam.updateThread.rstLoop10:                ; preds = %blockL114i2_114
  store i1 false, ptr %k2_vld6, align 1
  br label %blockL114i3_114

blockL114i3_114:                                  ; preds = %ExampleCam.updateThread.rstLoop10
  br label %ExampleCam.updateThread.rstLoop11

ExampleCam.updateThread.rstLoop11:                ; preds = %blockL114i3_114
  store i1 false, ptr %k3_vld8, align 1
  br label %blockL114i4_114

blockL114i4_114:                                  ; preds = %ExampleCam.updateThread.rstLoop11
  br label %block178

block178:                                         ; preds = %blockL114i4_114
  br label %blockL192i0_192

blockL192i0_192:                                  ; preds = %blockL192i0_534, %block178
  br label %blockL192i0_L214i0_214

blockL192i0_L214i0_214:                           ; preds = %blockL192i0_192
  br label %ExampleCam.updateThread.keyExportLoop

ExampleCam.updateThread.keyExportLoop:            ; preds = %blockL192i0_L214i0_214
  %k0_vld12 = load i1, ptr %k0_vld2, align 1
  %k0_key13 = load i16, ptr %k0_key1, align 2
  %0 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k0_key13, i1 %k0_vld12) #1
  store volatile i17 %0, ptr addrspace(1) %keyForMatchThread_0, align 4
  br label %blockL192i0_L214i1_214

blockL192i0_L214i1_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop
  br label %ExampleCam.updateThread.keyExportLoop1

ExampleCam.updateThread.keyExportLoop1:           ; preds = %blockL192i0_L214i1_214
  %k1_vld2 = load i1, ptr %k1_vld4, align 1
  %k1_key4 = load i16, ptr %k1_key3, align 2
  %1 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k1_key4, i1 %k1_vld2) #1
  store volatile i17 %1, ptr addrspace(2) %keyForMatchThread_1, align 4
  br label %blockL192i0_L214i2_214

blockL192i0_L214i2_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop1
  br label %ExampleCam.updateThread.keyExportLoop2

ExampleCam.updateThread.keyExportLoop2:           ; preds = %blockL192i0_L214i2_214
  %k2_vld3 = load i1, ptr %k2_vld6, align 1
  %k2_key4 = load i16, ptr %k2_key5, align 2
  %2 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k2_key4, i1 %k2_vld3) #1
  store volatile i17 %2, ptr addrspace(3) %keyForMatchThread_2, align 4
  br label %blockL192i0_L214i3_214

blockL192i0_L214i3_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop2
  br label %ExampleCam.updateThread.keyExportLoop3

ExampleCam.updateThread.keyExportLoop3:           ; preds = %blockL192i0_L214i3_214
  %k3_vld4 = load i1, ptr %k3_vld8, align 1
  %k3_key5 = load i16, ptr %k3_key7, align 2
  %3 = call i17 @hwtHls.bitConcat.i16.i1(i16 %k3_key5, i1 %k3_vld4) #1
  store volatile i17 %3, ptr addrspace(4) %keyForMatchThread_3, align 4
  br label %blockL192i0_L214i4_214

blockL192i0_L214i4_214:                           ; preds = %ExampleCam.updateThread.keyExportLoop3
  br label %ExampleCam.updateThread.keyUpdate

ExampleCam.updateThread.keyUpdate:                ; preds = %blockL192i0_L214i4_214
  %write_read_addr = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %write_read_addr, align 1
  %write_read_data = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %write_read_data, align 2
  %write_read_vld_flag = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %write_read_vld_flag, align 1
  %write_read_addr1 = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %write_read_addr1, align 1
  %write_read_data2 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %write_read_data2, align 2
  %write_read_vld_flag3 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %write_read_vld_flag3, align 1
  %write_read = alloca i19, align 4, !hwtHls.tmp.alloca !2
  store i19 undef, ptr %write_read, align 4
  %w_addr = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %w_addr, align 1
  %w_data = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %w_data, align 2
  %w_vld_flag = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %w_vld_flag, align 1
  %w_addr4 = alloca i2, align 1, !hwtHls.tmp.alloca !2
  store i2 undef, ptr %w_addr4, align 1
  %w_data5 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %w_data5, align 2
  %w_vld_flag6 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %w_vld_flag6, align 1
  %write_read1 = load volatile i19, ptr addrspace(5) %write, align 4
  store i19 %write_read1, ptr %write_read, align 4
  %write_read2 = load i19, ptr %write_read, align 4
  %write_read_vld_flag5 = call i1 @hwtHls.bitRangeGet.i19.i6.i1.18(i19 %write_read2, i6 18) #1
  %write_read_data4 = call i16 @hwtHls.bitRangeGet.i19.i6.i16.2(i19 %write_read2, i6 2) #1
  %write_read_addr3 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read2, i6 0) #1
  store i2 %write_read_addr3, ptr %w_addr4, align 1
  store i16 %write_read_data4, ptr %w_data5, align 2
  store i1 %write_read_vld_flag5, ptr %w_vld_flag6, align 1
  %newKey_key = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %newKey_key, align 2
  %newKey_vld = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %newKey_vld, align 1
  %newKey_key6 = alloca i16, align 2, !hwtHls.tmp.alloca !2
  store i16 undef, ptr %newKey_key6, align 2
  %newKey_vld7 = alloca i1, align 1, !hwtHls.tmp.alloca !2
  store i1 undef, ptr %newKey_vld7, align 1
  store i16 undef, ptr %newKey_key6, align 2
  store i1 undef, ptr %newKey_vld7, align 1
  store i1 %write_read_vld_flag5, ptr %newKey_vld7, align 1
  store i16 %write_read_data4, ptr %newKey_key6, align 2
  switch i2 %write_read_addr3, label %ExampleCam.updateThread.keyUpdate_518_setSwEnd [
    i2 0, label %ExampleCam.updateThread.keyUpdate_518_c0
    i2 1, label %ExampleCam.updateThread.keyUpdate_518_c1
    i2 -2, label %ExampleCam.updateThread.keyUpdate_518_c2
    i2 -1, label %ExampleCam.updateThread.keyUpdate_518_c3
  ]

ExampleCam.updateThread.keyUpdate_518_setSwEnd:   ; preds = %ExampleCam.updateThread.keyUpdate_518_c3, %ExampleCam.updateThread.keyUpdate_518_c2, %ExampleCam.updateThread.keyUpdate_518_c1, %ExampleCam.updateThread.keyUpdate_518_c0, %ExampleCam.updateThread.keyUpdate
  br label %blockL192i0_534

ExampleCam.updateThread.keyUpdate_518_c0:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key8 = load i16, ptr %newKey_key6, align 2
  store i16 %newKey_key8, ptr %k0_key1, align 2
  %newKey_vld9 = load i1, ptr %newKey_vld7, align 1
  store i1 %newKey_vld9, ptr %k0_vld2, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c1:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key10 = load i16, ptr %newKey_key6, align 2
  store i16 %newKey_key10, ptr %k1_key3, align 2
  %newKey_vld11 = load i1, ptr %newKey_vld7, align 1
  store i1 %newKey_vld11, ptr %k1_vld4, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c2:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key12 = load i16, ptr %newKey_key6, align 2
  store i16 %newKey_key12, ptr %k2_key5, align 2
  %newKey_vld13 = load i1, ptr %newKey_vld7, align 1
  store i1 %newKey_vld13, ptr %k2_vld6, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

ExampleCam.updateThread.keyUpdate_518_c3:         ; preds = %ExampleCam.updateThread.keyUpdate
  %newKey_key14 = load i16, ptr %newKey_key6, align 2
  store i16 %newKey_key14, ptr %k3_key7, align 2
  %newKey_vld15 = load i1, ptr %newKey_vld7, align 1
  store i1 %newKey_vld15, ptr %k3_vld8, align 1
  br label %ExampleCam.updateThread.keyUpdate_518_setSwEnd

blockL192i0_534:                                  ; preds = %ExampleCam.updateThread.keyUpdate_518_setSwEnd
  br label %blockL192i0_192
}
