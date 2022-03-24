define dso_local i32 @main() #0 {
mainThread:
  br [label %block26 ]
block26:
  br [label %block26i0_28 ]
block26i0_28:
  br [label %block26i1_26 ]
block26i1_26:
  br [label %block26i1_28 ]
block26i1_28:
  br [label %block26i2_26 ]
block26i2_26:
  br [label %block26i2_28 ]
block26i2_28:
  br [label %block26i3_26 ]
block26i3_26:
  br [label %block26i3_28 ]
block26i3_28:
  br [label %block26i4_26 ]
block26i4_26:
  br [label %block40 ]
block40:
  %2 = phi <Bits, 32bits, unsigned> [<BitsVal 0>, block26i4_26], [%27, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %4 = phi <Bits, 32bits, unsigned> [<BitsVal 0>, block26i4_26], [%29, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %6 = phi <Bits, 32bits, unsigned> [<BitsVal 0>, block26i4_26], [%31, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %7 = phi <Bits, 32bits, unsigned> [<BitsVal 0>, block26i4_26], [%33, block50_getSwEnd_getSwEnd_106_setSwEnd]
  br [label %block50 ]
block50:
  o_addr0 = call <Bits, 2bits, unsigned> @hls.read(o_addr)
  %1 = EQ o_addr0, <BitsVal 0>
  %3 = EQ o_addr0, <BitsVal 1>
  %5 = EQ o_addr0, <BitsVal 2>
  br [label %block50_62_c0 %1]
  [label %block50_62_c1 %3]
  [label %block50_62_c2 %5]
  [label %block50_62_c3 ]
block50_62_c0:
  br [label %block50_getSwEnd ]
block50_getSwEnd:
  %8 = phi <Bits, 32bits, unsigned> [%2, block50_62_c0], [%4, block50_62_c1], [%6, block50_62_c2], [%7, block50_62_c3]
  void call <Bits, 32bits, unsigned> @hls.write(o)
  i10 = call <Bits, 2bits, unsigned> @hls.read(i)
  %11 = EQ i10, <BitsVal 0>
  %13 = EQ i10, <BitsVal 1>
  %15 = EQ i10, <BitsVal 2>
  br [label %block50_getSwEnd_98_c0 %11]
  [label %block50_getSwEnd_98_c1 %13]
  [label %block50_getSwEnd_98_c2 %15]
  [label %block50_getSwEnd_98_c3 ]
block50_getSwEnd_98_c0:
  br [label %block50_getSwEnd_getSwEnd ]
block50_getSwEnd_getSwEnd:
  %20 = phi <Bits, 32bits, unsigned> [%2, block50_getSwEnd_98_c0], [%4, block50_getSwEnd_98_c1], [%6, block50_getSwEnd_98_c2], [%7, block50_getSwEnd_98_c3]
  %19 = EQ i10, <BitsVal 0>
  %22 = EQ i10, <BitsVal 1>
  %24 = EQ i10, <BitsVal 2>
  br [label %block50_getSwEnd_getSwEnd_106_c0 %19]
  [label %block50_getSwEnd_getSwEnd_106_c1 %22]
  [label %block50_getSwEnd_getSwEnd_106_c2 %24]
  [label %block50_getSwEnd_getSwEnd_106_c3 ]
block50_getSwEnd_getSwEnd_106_c0:
  %21 = ADD %20, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd_getSwEnd_106_setSwEnd:
  %27 = phi <Bits, 32bits, unsigned> [%21, block50_getSwEnd_getSwEnd_106_c0], [%2, block50_getSwEnd_getSwEnd_106_c1], [%2, block50_getSwEnd_getSwEnd_106_c2], [%2, block50_getSwEnd_getSwEnd_106_c3]
  %29 = phi <Bits, 32bits, unsigned> [%4, block50_getSwEnd_getSwEnd_106_c0], [%23, block50_getSwEnd_getSwEnd_106_c1], [%4, block50_getSwEnd_getSwEnd_106_c2], [%4, block50_getSwEnd_getSwEnd_106_c3]
  %31 = phi <Bits, 32bits, unsigned> [%6, block50_getSwEnd_getSwEnd_106_c0], [%6, block50_getSwEnd_getSwEnd_106_c1], [%25, block50_getSwEnd_getSwEnd_106_c2], [%6, block50_getSwEnd_getSwEnd_106_c3]
  %33 = phi <Bits, 32bits, unsigned> [%7, block50_getSwEnd_getSwEnd_106_c0], [%7, block50_getSwEnd_getSwEnd_106_c1], [%7, block50_getSwEnd_getSwEnd_106_c2], [%26, block50_getSwEnd_getSwEnd_106_c3]
  br [label %block40 ]
block50_getSwEnd_getSwEnd_106_c1:
  %23 = ADD %20, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd_getSwEnd_106_c2:
  %25 = ADD %20, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd_getSwEnd_106_c3:
  %26 = ADD %20, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd_98_c1:
  br [label %block50_getSwEnd_getSwEnd ]
block50_getSwEnd_98_c2:
  br [label %block50_getSwEnd_getSwEnd ]
block50_getSwEnd_98_c3:
  br [label %block50_getSwEnd_getSwEnd ]
block50_62_c1:
  br [label %block50_getSwEnd ]
block50_62_c2:
  br [label %block50_getSwEnd ]
block50_62_c3:
  br [label %block50_getSwEnd ]
}