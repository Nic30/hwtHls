"""
This file contains examples which do not work in llvm-18 with NewGVN but work with GVN
"""

# in this example %.phiConc1 is wrongly replaced with %.phiConc
# https://github.com/llvm/llvm-project/issues/70421
"""
define void @ExampleCam.updateThread(ptr addrspace(1) %keyForMatchThread_0, ptr addrspace(2) %keyForMatchThread_1, ptr addrspace(3) %write) {
bb0:
  br label %bb.header

bb.header:                                        ; preds = %bb.sw_c3, %bb.sw_c2, %bb.sw_c1, %bb.header, %bb0
  %.phiConc = phi i17 [ 0, %bb0 ], [ %.phiConc, %bb.sw_c3 ], [ %.phiConc, %bb.sw_c2 ], [ %.phiConc, %bb.sw_c1 ], [ %0, %bb.header ]
  %.phiConc1 = phi i17 [ 0, %bb0 ], [ %.phiConc1, %bb.sw_c3 ], [ %.phiConc1, %bb.sw_c2 ], [ %0, %bb.sw_c1 ], [ %.phiConc1, %bb.header ]
  store volatile i17 %.phiConc, ptr addrspace(1) %keyForMatchThread_0, align 4
  store volatile i17 %.phiConc1, ptr addrspace(2) %keyForMatchThread_1, align 4
  %write_read = load volatile i19, ptr addrspace(3) %write, align 4
  %0 = call i17 @hwtHls.bitRangeGet.i19.i6.i17.2(i19 %write_read, i6 2) #1
  %1 = call i2 @hwtHls.bitRangeGet.i19.i6.i2.0(i19 %write_read, i6 0) #1
  switch i2 %1, label %bb.header.unreachabledefault [
    i2 0, label %bb.header
    i2 1, label %bb.sw_c1
    i2 -2, label %bb.sw_c2
    i2 -1, label %bb.sw_c3
  ]

bb.header.unreachabledefault:                     ; preds = %bb.header
  unreachable

bb.sw_c1:                                         ; preds = %bb.header
  br label %bb.header

bb.sw_c2:                                         ; preds = %bb.header
  br label %bb.header

bb.sw_c3:                                         ; preds = %bb.header
  br label %bb.header
}
"""