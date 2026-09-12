define void @test_multiPhi0(ptr addrspace(1) %i, ptr addrspace(2) %o) {
bb0:
  %bb3.ioFsmStBefore.IoFsmSt = alloca i3, align 1
  store i3 0, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  br label %bb27

bb27:                                             ; preds = %bb45, %bb0
  %i_read1.r0.data.reg2mem.2.reg2mem.0 = phi i16 [ %i_read1.r0.data.reg2mem.3.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %i_read3.r0.data.reg2mem.0.reg2mem.0 = phi i16 [ %i_read3.r0.data.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %i_read3.r0.eof.reg2mem.0.reg2mem.0 = phi i1 [ %i_read3.r0.eof.reg2mem.1.ph.1lane, %bb45 ], [ undef, %bb0 ]
  %0 = load i3, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %1 = load volatile i38, ptr addrspace(1) %i, align 8
  %i_read1.r0.empty.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.37(i38 %1, i7 37) #1
  %i_read1.r0.eof.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.36(i38 %1, i7 36) #1
  %2 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.24(i38 %1, i7 24) #1
  %3 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.16(i38 %1, i7 16) #1
  %i_read1.r0.enable.1lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.35(i38 %1, i7 35) #1
  %i_read1.r0.empty.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.34(i38 %1, i7 34) #1
  %i_read1.r0.eof.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.33(i38 %1, i7 33) #1
  %4 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.8(i38 %1, i7 8) #1
  %5 = call i8 @hwtHls.bitRangeGet.i38.i7.i8.0(i38 %1, i7 0) #1
  %i_read1.r0.enable.0lane = call i1 @hwtHls.bitRangeGet.i38.i7.i1.32(i38 %1, i7 32) #1
  %6 = call i16 @hwtHls.bitRangeGet.i38.i7.i16.16(i38 %1, i7 16) #1
  %7 = call i16 @hwtHls.bitRangeGet.i38.i7.i16.0(i38 %1, i7 0) #1
  %8 = xor i1 %i_read1.r0.empty.0lane, true
  %9 = or i1 %i_read1.r0.eof.0lane, %8
  %fewExitSw.sucSel.en..bb4.0lane = icmp eq i16 %i_read1.r0.data.reg2mem.2.reg2mem.0, 3
  %10 = and i1 %i_read1.r0.eof.0lane, %i_read1.r0.empty.0lane
  %11 = or i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0, %10
  %12 = and i1 %11, %i_read1.r0.empty.0lane
  %"(i_read3).0lane" = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %i_read3.r0.data.reg2mem.0.reg2mem.0, i8 %5, i1 %12) #1
  %i_read_data4.0lane = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %"(i_read3).0lane", i6 0) #1
  %13 = xor i1 %11, true
  %spec.select.0lane = call i4 @hwtHls.bitConcat.i3.i1(i3 0, i1 %13) #1
  %14 = icmp eq i4 %spec.select.0lane, 0
  %15 = or i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0, %i_read1.r0.eof.0lane
  %"(i_read11).0lane" = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %i_read3.r0.data.reg2mem.0.reg2mem.0, i16 %7, i1 %15) #1
  %16 = call i24 @hwtHls.bitRangeGet.i33.i7.i24.0(i33 %"(i_read11).0lane", i7 0) #1
  %17 = call i3 @hwtHls.bitConcat.i1.i2(i1 %fewExitSw.sucSel.en..bb4.0lane, i2 1) #1
  switch i3 %0, label %bb25 [
    i3 0, label %bb30
    i3 1, label %bb44
    i3 2, label %bb40
    i3 3, label %bb34
    i3 -4, label %bb38
  ]

bb30:                                             ; preds = %bb27
  br i1 %i_read1.r0.enable.0lane, label %bb32, label %bb44

bb31:                                             ; preds = %bb44
  br i1 %i_read1.r0.enable.1lane, label %bb33, label %bb45

bb32:                                             ; preds = %bb30
  %18 = icmp eq i16 %7, 3
  %19 = icmp eq i16 %7, 4
  %20 = or i1 %18, %19
  %21 = xor i1 %20, true
  %fewExitSw.sucSel.en.bb32.bb36 = or i1 false, %21
  %fewExitSw.sucSel.en.bb32.bb42 = icmp eq i16 %7, 4
  %br.bb42.enFor.bb44 = and i1 %fewExitSw.sucSel.en.bb32.bb42, true
  %fewExitSw.sucSel.en.bb32.bb44 = icmp eq i16 %7, 3
  %22 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i3 1, i3 1
  %23 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i1 false, i1 false
  %24 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i32 poison, i32 poison
  %25 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i1 false, i1 false
  %26 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i32 poison, i32 poison
  %27 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0, i1 %i_read3.r0.eof.reg2mem.0.reg2mem.0
  %28 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i16 %i_read3.r0.data.reg2mem.0.reg2mem.0, i16 %i_read3.r0.data.reg2mem.0.reg2mem.0
  %29 = select i1 %fewExitSw.sucSel.en.bb32.bb44, i16 %7, i16 %7
  br i1 %fewExitSw.sucSel.en.bb32.bb36, label %bb36, label %bb44

bb33:                                             ; preds = %bb31
  %30 = icmp eq i16 %6, 3
  %31 = icmp eq i16 %6, 4
  %32 = or i1 %30, %31
  %33 = xor i1 %32, true
  %fewExitSw.sucSel.en.bb33.bb37 = or i1 false, %33
  %fewExitSw.sucSel.en.bb33.bb43 = icmp eq i16 %6, 4
  %br.bb43.enFor.bb45 = and i1 %fewExitSw.sucSel.en.bb33.bb43, true
  %fewExitSw.sucSel.en.bb33.bb45 = icmp eq i16 %6, 3
  %34 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i3 1, i3 1
  %35 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i1 false, i1 false
  %36 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i32 poison, i32 poison
  %37 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i1 false, i1 false
  %38 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i32 poison, i32 poison
  %39 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i1 %i_read3.r0.eof.reg2mem.1.ph.0lane, i1 %i_read3.r0.eof.reg2mem.1.ph.0lane
  %40 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i16 %i_read3.r0.data.reg2mem.1.ph.0lane, i16 %i_read3.r0.data.reg2mem.1.ph.0lane
  %41 = select i1 %fewExitSw.sucSel.en.bb33.bb45, i16 %6, i16 %6
  br i1 %fewExitSw.sucSel.en.bb33.bb37, label %bb37, label %bb45

bb34:                                             ; preds = %bb40, %bb27
  %iDataOffset.1.0lane = phi i1 [ true, %bb40 ], [ %14, %bb27 ]
  %42 = phi i24 [ %16, %bb40 ], [ %i_read_data4.0lane, %bb27 ]
  %43 = phi i8 [ %4, %bb40 ], [ 0, %bb27 ]
  %44 = call i32 @hwtHls.bitConcat.i24.i8(i24 %42, i8 %43) #1
  br i1 %iDataOffset.1.0lane, label %bb36, label %bb38

bb35:                                             ; preds = %bb44, %bb41
  %iDataOffset.1.1lane = phi i1 [ true, %bb41 ], [ %59, %bb44 ]
  %45 = phi i24 [ %61, %bb41 ], [ %i_read_data4.1lane, %bb44 ]
  %46 = phi i8 [ %2, %bb41 ], [ 0, %bb44 ]
  %47 = call i32 @hwtHls.bitConcat.i24.i8(i24 %45, i8 %46) #1
  br i1 %iDataOffset.1.1lane, label %bb37, label %bb39

bb36:                                             ; preds = %bb32, %bb34
  %storeLaneVld0.2.0lane = phi i1 [ false, %bb32 ], [ true, %bb34 ]
  %storeLaneData0.2.0lane = phi i32 [ poison, %bb32 ], [ %44, %bb34 ]
  %i_read1.r0.data.reg2mem.1.0lane = phi i16 [ %7, %bb32 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb34 ]
  br label %bb44

bb37:                                             ; preds = %bb33, %bb35
  %storeLaneVld0.2.1lane = phi i1 [ false, %bb33 ], [ true, %bb35 ]
  %storeLaneData0.2.1lane = phi i32 [ poison, %bb33 ], [ %47, %bb35 ]
  %i_read1.r0.data.reg2mem.1.1lane = phi i16 [ %6, %bb33 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb35 ]
  br label %bb45

bb38:                                             ; preds = %bb34, %bb27
  %storeLaneVld0.0.0lane = phi i1 [ true, %bb34 ], [ false, %bb27 ]
  %storeLaneData0.0.0lane = phi i32 [ %44, %bb34 ], [ poison, %bb27 ]
  %iDataOffset.0.0.0lane = phi i1 [ false, %bb34 ], [ true, %bb27 ]
  %"(i_read5).0lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %5, i1 %10) #1
  %"(i_read5)21.0lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %4, i1 %i_read1.r0.eof.0lane) #1
  %"(i_read5).mux.0lane" = select i1 %iDataOffset.0.0.0lane, i9 %"(i_read5).0lane", i9 %"(i_read5)21.0lane"
  %i_read_data7.0lane = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %"(i_read5).mux.0lane", i5 0) #1
  %48 = zext i8 %i_read_data7.0lane to i32
  br label %bb44

bb39:                                             ; preds = %bb44, %bb35
  %storeLaneVld0.0.1lane = phi i1 [ true, %bb35 ], [ false, %bb44 ]
  %storeLaneData0.0.1lane = phi i32 [ %47, %bb35 ], [ poison, %bb44 ]
  %iDataOffset.0.0.1lane = phi i1 [ false, %bb35 ], [ true, %bb44 ]
  %"(i_read5).1lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %3, i1 %55) #1
  %"(i_read5)21.1lane" = call i9 @hwtHls.bitConcat.i8.i1(i8 %2, i1 %i_read1.r0.eof.1lane) #1
  %"(i_read5).mux.1lane" = select i1 %iDataOffset.0.0.1lane, i9 %"(i_read5).1lane", i9 %"(i_read5)21.1lane"
  %i_read_data7.1lane = call i8 @hwtHls.bitRangeGet.i9.i5.i8.0(i9 %"(i_read5).mux.1lane", i5 0) #1
  %49 = zext i8 %i_read_data7.1lane to i32
  br label %bb45

bb40:                                             ; preds = %bb27
  br label %bb34

bb41:                                             ; preds = %bb44
  br label %bb35

bb44:                                             ; preds = %bb32, %bb38, %bb36, %bb30, %bb27
  %.sink.0lane = phi i3 [ %22, %bb32 ], [ 0, %bb38 ], [ -4, %bb36 ], [ 0, %bb30 ], [ %17, %bb27 ]
  %storeLaneVld1.1.ph.0lane = phi i1 [ %23, %bb32 ], [ true, %bb38 ], [ false, %bb36 ], [ false, %bb30 ], [ false, %bb27 ]
  %storeLaneData1.1.ph.0lane = phi i32 [ %24, %bb32 ], [ %48, %bb38 ], [ poison, %bb36 ], [ poison, %bb30 ], [ poison, %bb27 ]
  %storeLaneVld0.3.ph.0lane = phi i1 [ %25, %bb32 ], [ %storeLaneVld0.0.0lane, %bb38 ], [ %storeLaneVld0.2.0lane, %bb36 ], [ false, %bb30 ], [ false, %bb27 ]
  %storeLaneData0.3.ph.0lane = phi i32 [ %26, %bb32 ], [ %storeLaneData0.0.0lane, %bb38 ], [ %storeLaneData0.2.0lane, %bb36 ], [ poison, %bb30 ], [ poison, %bb27 ]
  %i_read3.r0.eof.reg2mem.1.ph.0lane = phi i1 [ %27, %bb32 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb38 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb36 ], [ %i_read3.r0.eof.reg2mem.0.reg2mem.0, %bb30 ], [ %i_read1.r0.eof.0lane, %bb27 ]
  %i_read3.r0.data.reg2mem.1.ph.0lane = phi i16 [ %28, %bb32 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb38 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb36 ], [ %i_read3.r0.data.reg2mem.0.reg2mem.0, %bb30 ], [ %7, %bb27 ]
  %i_read1.r0.data.reg2mem.3.ph.0lane = phi i16 [ %29, %bb32 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb38 ], [ %i_read1.r0.data.reg2mem.1.0lane, %bb36 ], [ %7, %bb30 ], [ %i_read1.r0.data.reg2mem.2.reg2mem.0, %bb27 ]
  store i3 %.sink.0lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %50 = call i66 @hwtHls.bitConcat.i32.i32.i1.i1(i32 %storeLaneData0.3.ph.0lane, i32 %storeLaneData1.1.ph.0lane, i1 %storeLaneVld0.3.ph.0lane, i1 %storeLaneVld1.1.ph.0lane) #1
  %51 = call i64 @hwtHls.bitRangeGet.i66.i8.i64.0(i66 %50, i8 0) #1
  %52 = call i2 @hwtHls.bitRangeGet.i66.i8.i2.64(i66 %50, i8 64) #1
  %53 = xor i1 %i_read1.r0.empty.1lane, true
  %54 = or i1 %i_read1.r0.eof.1lane, %53
  %fewExitSw.sucSel.en..bb4.1lane = icmp eq i16 %i_read1.r0.data.reg2mem.3.ph.0lane, 3
  %55 = and i1 %i_read1.r0.eof.1lane, %i_read1.r0.empty.1lane
  %56 = or i1 %i_read3.r0.eof.reg2mem.1.ph.0lane, %55
  %57 = and i1 %56, %i_read1.r0.empty.1lane
  %"(i_read3).1lane" = call i25 @hwtHls.bitConcat.i16.i8.i1(i16 %i_read3.r0.data.reg2mem.1.ph.0lane, i8 %3, i1 %57) #1
  %i_read_data4.1lane = call i24 @hwtHls.bitRangeGet.i25.i6.i24.0(i25 %"(i_read3).1lane", i6 0) #1
  %58 = xor i1 %56, true
  %spec.select.1lane = call i4 @hwtHls.bitConcat.i3.i1(i3 0, i1 %58) #1
  %59 = icmp eq i4 %spec.select.1lane, 0
  %60 = or i1 %i_read3.r0.eof.reg2mem.1.ph.0lane, %i_read1.r0.eof.1lane
  %"(i_read11).1lane" = call i33 @hwtHls.bitConcat.i16.i16.i1(i16 %i_read3.r0.data.reg2mem.1.ph.0lane, i16 %6, i1 %60) #1
  %61 = call i24 @hwtHls.bitRangeGet.i33.i7.i24.0(i33 %"(i_read11).1lane", i7 0) #1
  %62 = call i3 @hwtHls.bitConcat.i1.i2(i1 %fewExitSw.sucSel.en..bb4.1lane, i2 1) #1
  switch i3 %.sink.0lane, label %bb25 [
    i3 0, label %bb31
    i3 1, label %bb45
    i3 2, label %bb41
    i3 3, label %bb35
    i3 -4, label %bb39
  ]

bb45:                                             ; preds = %bb33, %bb44, %bb39, %bb37, %bb31
  %.sink.1lane = phi i3 [ %34, %bb33 ], [ %62, %bb44 ], [ 0, %bb39 ], [ -4, %bb37 ], [ 0, %bb31 ]
  %storeLaneVld1.1.ph.1lane = phi i1 [ %35, %bb33 ], [ false, %bb44 ], [ true, %bb39 ], [ false, %bb37 ], [ false, %bb31 ]
  %storeLaneData1.1.ph.1lane = phi i32 [ %36, %bb33 ], [ poison, %bb44 ], [ %49, %bb39 ], [ poison, %bb37 ], [ poison, %bb31 ]
  %storeLaneVld0.3.ph.1lane = phi i1 [ %37, %bb33 ], [ false, %bb44 ], [ %storeLaneVld0.0.1lane, %bb39 ], [ %storeLaneVld0.2.1lane, %bb37 ], [ false, %bb31 ]
  %storeLaneData0.3.ph.1lane = phi i32 [ %38, %bb33 ], [ poison, %bb44 ], [ %storeLaneData0.0.1lane, %bb39 ], [ %storeLaneData0.2.1lane, %bb37 ], [ poison, %bb31 ]
  %i_read3.r0.eof.reg2mem.1.ph.1lane = phi i1 [ %39, %bb33 ], [ %i_read1.r0.eof.1lane, %bb44 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb39 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb37 ], [ %i_read3.r0.eof.reg2mem.1.ph.0lane, %bb31 ]
  %i_read3.r0.data.reg2mem.1.ph.1lane = phi i16 [ %40, %bb33 ], [ %6, %bb44 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb39 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb37 ], [ %i_read3.r0.data.reg2mem.1.ph.0lane, %bb31 ]
  %i_read1.r0.data.reg2mem.3.ph.1lane = phi i16 [ %41, %bb33 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb44 ], [ %i_read1.r0.data.reg2mem.3.ph.0lane, %bb39 ], [ %i_read1.r0.data.reg2mem.1.1lane, %bb37 ], [ %6, %bb31 ]
  store i3 %.sink.1lane, ptr %bb3.ioFsmStBefore.IoFsmSt, align 1
  %63 = call i66 @hwtHls.bitConcat.i32.i32.i1.i1(i32 %storeLaneData0.3.ph.1lane, i32 %storeLaneData1.1.ph.1lane, i1 %storeLaneVld0.3.ph.1lane, i1 %storeLaneVld1.1.ph.1lane) #1
  %64 = call i64 @hwtHls.bitRangeGet.i66.i8.i64.0(i66 %63, i8 0) #1
  %65 = call i2 @hwtHls.bitRangeGet.i66.i8.i2.64(i66 %63, i8 64) #1
  %66 = call i132 @hwtHls.bitConcat.i64.i64.i2.i2(i64 %51, i64 %64, i2 %52, i2 %65) #1
  store volatile i132 %66, ptr addrspace(2) %o, align 32
  br label %bb27

bb25:                                             ; preds = %bb44, %bb27
  unreachable
}
