define void @CountLeadingZeros.mainThread(ptr addrspace(1) %data_in, ptr addrspace(2) %data_out) !hwtHls.param_addr_width !0 {
CountLeadingZeros.mainThread:
  br label %block0

block0:                                           ; preds = %CountLeadingZeros.mainThread
  br label %blockL42i0_42

blockL42i0_42:                                    ; preds = %blockL42i0_42_afterCall, %block0
  %"data_in0(data_in_read)" = load volatile i4, ptr addrspace(1) %data_in, align 1
  %0 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.3(i4 %"data_in0(data_in_read)", i3 3) #1
  %1 = call i1 @hwtHls.bitRangeGet.i4.i3.i1.1(i4 %"data_in0(data_in_read)", i3 1) #1
  %2 = call i2 @hwtHls.bitRangeGet.i4.i3.i2.2(i4 %"data_in0(data_in_read)", i3 2) #1
  br label %"blockL42i0_(countBits, 168)_0"

"blockL42i0_(countBits, 168)_0":                  ; preds = %blockL42i0_42
  br label %"blockL42i0_(countBits, 168)_80"

"blockL42i0_(countBits, 168)_80":                 ; preds = %"blockL42i0_(countBits, 168)_0"
  br label %"blockL42i0_(countBits, 168)_142"

"blockL42i0_(countBits, 168)_142":                ; preds = %"blockL42i0_(countBits, 168)_80"
  br label %"blockL42i0_(countBits, 168)_154"

"blockL42i0_(countBits, 168)_154":                ; preds = %"blockL42i0_(countBits, 168)_142"
  %"2" = icmp eq i4 %"data_in0(data_in_read)", 0
  br label %"blockL42i0_(countBits, 168)_266"

"blockL42i0_(countBits, 168)_266":                ; preds = %"blockL42i0_(countBits, 168)_154"
  br label %"blockL42i0_(countBits, 168)_284"

"blockL42i0_(countBits, 168)_284":                ; preds = %"blockL42i0_(countBits, 168)_266"
  br label %"blockL42i0_(countBits, 168)_310"

"blockL42i0_(countBits, 168)_310":                ; preds = %"blockL42i0_(countBits, 168)_284"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_0"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_0": ; preds = %"blockL42i0_(countBits, 168)_310"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_30"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_30": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_0"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_138"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_138": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_30"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_170"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_170": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_138"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_234"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_234": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_170"
  %"7" = icmp eq i2 %2, 0
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_392"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_392": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_234"
  br i1 %"7", label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_448", label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_454"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_448": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_392"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_454", %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_448"
  %"%13(in_)1" = phi i1 [ %1, %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_448" ], [ %0, %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_454" ]
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_0"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_0": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_30"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_30": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_0"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_92"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_92": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_30"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_104"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_104": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_92"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458_afterCall"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458_afterCall": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_(_countLeadingRecurse, 506)_104"
  %"12" = xor i1 %"%13(in_)1", true
  br label %"blockL42i0_(countBits, 168)_310_afterCall"

"blockL42i0_(countBits, 168)_310_afterCall":      ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458_afterCall"
  br i1 %"2", label %"blockL42i0_(countBits, 168)_448", label %"blockL42i0_(countBits, 168)_454"

"blockL42i0_(countBits, 168)_448":                ; preds = %"blockL42i0_(countBits, 168)_310_afterCall"
  br label %"blockL42i0_(countBits, 168)_522"

"blockL42i0_(countBits, 168)_522":                ; preds = %"blockL42i0_(countBits, 168)_454", %"blockL42i0_(countBits, 168)_448"
  %"%37(dataOut)" = phi i3 [ -4, %"blockL42i0_(countBits, 168)_448" ], [ %3, %"blockL42i0_(countBits, 168)_454" ]
  br label %blockL42i0_42_afterCall

blockL42i0_42_afterCall:                          ; preds = %"blockL42i0_(countBits, 168)_522"
  store volatile i3 %"%37(dataOut)", ptr addrspace(2) %data_out, align 1
  br label %blockL42i0_42

"blockL42i0_(countBits, 168)_454":                ; preds = %"blockL42i0_(countBits, 168)_310_afterCall"
  %3 = call i3 @hwtHls.bitConcat.i1.i1.i1(i1 %"12", i1 %"7", i1 false) #1
  br label %"blockL42i0_(countBits, 168)_522"

"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_454": ; preds = %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_392"
  br label %"blockL42i0_(countBits, 168)_(_countLeadingRecurse, 332)_458"
}
