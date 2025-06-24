define void @_BaseALU1HwModule.mainThread(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) !hwtHls.io !0 {
bb0:
  br label %block0

block0:                                           ; preds = %bb0
  br label %block134

block134:                                         ; preds = %block0
  br label %blockL146i0_146

blockL146i0_146:                                  ; preds = %blockL146i0_346, %block134
  %data_in_read = alloca i4, align 1, !hwtHls.tmp.alloca !4
  store i4 undef, ptr %data_in_read, align 1
  %inp = alloca i4, align 1, !hwtHls.tmp.alloca !4
  store i4 undef, ptr %inp, align 1
  %data_in_read1 = load volatile i4, ptr addrspace(1) %data_in, align 1
  store i4 %data_in_read1, ptr %data_in_read, align 1
  %data_in_read2 = load i4, ptr %data_in_read, align 1
  store i4 %data_in_read2, ptr %inp, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_0"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_0":   ; preds = %blockL146i0_146
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_80"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_80":  ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_0"
  %_i = alloca i4, align 1, !hwtHls.tmp.alloca !4
  store i4 undef, ptr %_i, align 1
  %inp3 = load i4, ptr %inp, align 1
  store i4 %inp3, ptr %_i, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_186"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_186": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_80"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_0"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_0": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_186"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_76"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_76": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_0"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_122"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_122": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_76"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_132"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_132": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_122"
  %full = alloca i1, align 1, !hwtHls.tmp.alloca !4
  store i1 undef, ptr %full, align 1
  %_i4 = load i4, ptr %_i, align 1
  %full5 = icmp eq i4 %_i4, 0
  store i1 %full5, ptr %full, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_220"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_220": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_132"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_224"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_224": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_220"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_224"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_0"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_0": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_24"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_24": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_0"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_118"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_118": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_24"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_142"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_142": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_118"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_172"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_172": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_142"
  %lhs = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %lhs, align 1
  %_i6 = load i4, ptr %_i, align 1
  %rhs8 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.0(i4 %_i6, i3 0) #1
  %lhs7 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %_i6, i3 2) #1
  store i2 %lhs7, ptr %lhs, align 1
  %rhs = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %rhs, align 1
  store i2 %rhs8, ptr %rhs, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_214"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_214": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_172"
  %leftFull = alloca i1, align 1, !hwtHls.tmp.alloca !4
  store i1 undef, ptr %leftFull, align 1
  %lhs9 = load i2, ptr %lhs, align 1
  %leftFull10 = icmp eq i2 %lhs9, 0
  store i1 %leftFull10, ptr %leftFull, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_350"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_350": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_214"
  %in_ = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %in_, align 1
  store i2 undef, ptr %in_, align 1
  %leftFull11 = load i1, ptr %leftFull, align 1
  br i1 %leftFull11, label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_408", label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_414"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_408": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_350"
  %rhs12 = load i2, ptr %rhs, align 1
  store i2 %rhs12, ptr %in_, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_414", %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_408"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_0"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_0": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_24"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_24": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_0"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_86"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_86": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_24"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_96"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_96": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_86"
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418_afterCall"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418_afterCall": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_(_countLeadingRecurse, 452)_96"
  %halfCount = alloca i1, align 1, !hwtHls.tmp.alloca !4
  store i1 undef, ptr %halfCount, align 1
  %in_13 = load i2, ptr %in_, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i2.i2.i1.1(i2 %in_13, i2 1) #1
  %halfCount14 = xor i1 %0, true
  store i1 %halfCount14, ptr %halfCount, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246_afterCall"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_414": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_350"
  %lhs15 = load i2, ptr %lhs, align 1
  store i2 %lhs15, ptr %in_, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246_afterCall": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_(_countLeadingRecurse, 274)_418_afterCall"
  %halfCount16 = alloca i2, align 1, !hwtHls.tmp.alloca !4
  store i2 undef, ptr %halfCount16, align 1
  %leftFull17 = load i1, ptr %leftFull, align 1
  %halfCount18 = load i1, ptr %halfCount, align 1
  %1 = call i2 @hwtHls.bitConcat.i1.i1(i1 %halfCount18, i1 %leftFull17) #1
  store i2 %1, ptr %halfCount16, align 1
  %dataOut = alloca i3, align 1, !hwtHls.tmp.alloca !4
  store i3 undef, ptr %dataOut, align 1
  store i3 undef, ptr %dataOut, align 1
  %full20 = load i1, ptr %full, align 1
  br i1 %full20, label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_364", label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_372"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_364": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246_afterCall"
  store i3 -4, ptr %dataOut, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_186_afterCall"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_372": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_246_afterCall"
  %halfCount21 = load i2, ptr %halfCount16, align 1
  %2 = zext i2 %halfCount21 to i3
  store i3 %2, ptr %dataOut, align 1
  br label %"blockL146i0_(CountLeadingZeros.aluFn, 264)_186_afterCall"

"blockL146i0_(CountLeadingZeros.aluFn, 264)_186_afterCall": ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_372", %"blockL146i0_(CountLeadingZeros.aluFn, 264)_(countBits, 222)_364"
  %res = alloca i3, align 1, !hwtHls.tmp.alloca !4
  store i3 undef, ptr %res, align 1
  %dataOut22 = load i3, ptr %dataOut, align 1
  store i3 %dataOut22, ptr %res, align 1
  br label %blockL146i0_146_afterCall

blockL146i0_146_afterCall:                        ; preds = %"blockL146i0_(CountLeadingZeros.aluFn, 264)_186_afterCall"
  %resTmp = alloca i3, align 1, !hwtHls.tmp.alloca !4
  store i3 undef, ptr %resTmp, align 1
  %res23 = load i3, ptr %res, align 1
  store i3 %res23, ptr %resTmp, align 1
  store volatile i3 %res23, ptr addrspace(2) %data_out, align 1
  br label %blockL146i0_346

blockL146i0_346:                                  ; preds = %blockL146i0_146_afterCall
  br label %blockL146i0_146
}
