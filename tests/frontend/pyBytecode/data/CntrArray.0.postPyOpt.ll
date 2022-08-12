define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL30i0_30 ]
blockL30i0_30:
  br [label %blockL30i0_32 ]
blockL30i0_32:
  br [label %blockL30i1_30 ]
blockL30i1_30:
  br [label %blockL30i1_32 ]
blockL30i1_32:
  br [label %blockL30i2_30 ]
blockL30i2_30:
  br [label %blockL30i2_32 ]
blockL30i2_32:
  br [label %blockL30i3_30 ]
blockL30i3_30:
  br [label %blockL30i3_32 ]
blockL30i3_32:
  br [label %blockL30i4_30 ]
blockL30i4_30:
  br [label %block44 ]
block44:
  br [label %blockL54i0_54 ]
blockL54i0_54:
  %2 = phi <Bits, 16bits, unsigned> [<BitsVal 0>, block44], [%27, blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd]
  %4 = phi <Bits, 16bits, unsigned> [<BitsVal 0>, block44], [%29, blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd]
  %6 = phi <Bits, 16bits, unsigned> [<BitsVal 0>, block44], [%31, blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd]
  %7 = phi <Bits, 16bits, unsigned> [<BitsVal 0>, block44], [%33, blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd]
  o_addr0 = call <Bits, 2bits, unsigned> @hls.read(o_addr)
  %1 = EQ o_addr0, <BitsVal 0>
  %3 = EQ o_addr0, <BitsVal 1>
  %5 = EQ o_addr0, <BitsVal 2>
  br [label %blockL54i0_54_66_c0 %1]
  [label %blockL54i0_54_66_c1 %3]
  [label %blockL54i0_54_66_c2 %5]
  [label %blockL54i0_54_66_c3 ]
blockL54i0_54_66_c0:
  br [label %blockL54i0_54_getSwEnd ]
blockL54i0_54_getSwEnd:
  %8 = phi <Bits, 16bits, unsigned> [%2, blockL54i0_54_66_c0], [%4, blockL54i0_54_66_c1], [%6, blockL54i0_54_66_c2], [%7, blockL54i0_54_66_c3]
  void call <Bits, 16bits, unsigned> @hls.write(o)
  i10 = call <Bits, 2bits, unsigned> @hls.read(i)
  %11 = EQ i10, <BitsVal 0>
  %13 = EQ i10, <BitsVal 1>
  %15 = EQ i10, <BitsVal 2>
  br [label %blockL54i0_54_getSwEnd_102_c0 %11]
  [label %blockL54i0_54_getSwEnd_102_c1 %13]
  [label %blockL54i0_54_getSwEnd_102_c2 %15]
  [label %blockL54i0_54_getSwEnd_102_c3 ]
blockL54i0_54_getSwEnd_102_c0:
  br [label %blockL54i0_54_getSwEnd_getSwEnd ]
blockL54i0_54_getSwEnd_getSwEnd:
  %20 = phi <Bits, 16bits, unsigned> [%2, blockL54i0_54_getSwEnd_102_c0], [%4, blockL54i0_54_getSwEnd_102_c1], [%6, blockL54i0_54_getSwEnd_102_c2], [%7, blockL54i0_54_getSwEnd_102_c3]
  %19 = EQ i10, <BitsVal 0>
  %22 = EQ i10, <BitsVal 1>
  %24 = EQ i10, <BitsVal 2>
  br [label %blockL54i0_54_getSwEnd_getSwEnd_110_c0 %19]
  [label %blockL54i0_54_getSwEnd_getSwEnd_110_c1 %22]
  [label %blockL54i0_54_getSwEnd_getSwEnd_110_c2 %24]
  [label %blockL54i0_54_getSwEnd_getSwEnd_110_c3 ]
blockL54i0_54_getSwEnd_getSwEnd_110_c0:
  %21 = ADD %20, <BitsVal 1>
  br [label %blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd ]
blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd:
  %27 = phi <Bits, 16bits, unsigned> [%21, blockL54i0_54_getSwEnd_getSwEnd_110_c0], [%2, blockL54i0_54_getSwEnd_getSwEnd_110_c1], [%2, blockL54i0_54_getSwEnd_getSwEnd_110_c2], [%2, blockL54i0_54_getSwEnd_getSwEnd_110_c3]
  %29 = phi <Bits, 16bits, unsigned> [%4, blockL54i0_54_getSwEnd_getSwEnd_110_c0], [%23, blockL54i0_54_getSwEnd_getSwEnd_110_c1], [%4, blockL54i0_54_getSwEnd_getSwEnd_110_c2], [%4, blockL54i0_54_getSwEnd_getSwEnd_110_c3]
  %31 = phi <Bits, 16bits, unsigned> [%6, blockL54i0_54_getSwEnd_getSwEnd_110_c0], [%6, blockL54i0_54_getSwEnd_getSwEnd_110_c1], [%25, blockL54i0_54_getSwEnd_getSwEnd_110_c2], [%6, blockL54i0_54_getSwEnd_getSwEnd_110_c3]
  %33 = phi <Bits, 16bits, unsigned> [%7, blockL54i0_54_getSwEnd_getSwEnd_110_c0], [%7, blockL54i0_54_getSwEnd_getSwEnd_110_c1], [%7, blockL54i0_54_getSwEnd_getSwEnd_110_c2], [%26, blockL54i0_54_getSwEnd_getSwEnd_110_c3]
  br [label %blockL54i0_54 ]
blockL54i0_54_getSwEnd_getSwEnd_110_c1:
  %23 = ADD %20, <BitsVal 1>
  br [label %blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd ]
blockL54i0_54_getSwEnd_getSwEnd_110_c2:
  %25 = ADD %20, <BitsVal 1>
  br [label %blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd ]
blockL54i0_54_getSwEnd_getSwEnd_110_c3:
  %26 = ADD %20, <BitsVal 1>
  br [label %blockL54i0_54_getSwEnd_getSwEnd_110_setSwEnd ]
blockL54i0_54_getSwEnd_102_c1:
  br [label %blockL54i0_54_getSwEnd_getSwEnd ]
blockL54i0_54_getSwEnd_102_c2:
  br [label %blockL54i0_54_getSwEnd_getSwEnd ]
blockL54i0_54_getSwEnd_102_c3:
  br [label %blockL54i0_54_getSwEnd_getSwEnd ]
blockL54i0_54_66_c1:
  br [label %blockL54i0_54_getSwEnd ]
blockL54i0_54_66_c2:
  br [label %blockL54i0_54_getSwEnd ]
blockL54i0_54_66_c3:
  br [label %blockL54i0_54_getSwEnd ]
}