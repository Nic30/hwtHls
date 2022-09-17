define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL40i0_40 ]
blockL40i0_40:
  i0 = call <Bits, 2bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 0>
  %2 = EQ i0, <BitsVal 1>
  %3 = EQ i0, <BitsVal 2>
  br [label %blockL40i0_40_58_c0 %1]
  [label %blockL40i0_40_58_c1 %2]
  [label %blockL40i0_40_58_c2 %3]
  [label %blockL40i0_40_58_c3 ]
blockL40i0_40_58_c0:
  br [label %blockL40i0_40_getSwEnd ]
blockL40i0_40_getSwEnd:
  %4 = phi <Bits, 32bits, unsigned> [<BitsVal 1>, blockL40i0_40_58_c0], [<BitsVal 2>, blockL40i0_40_58_c1], [<BitsVal 4>, blockL40i0_40_58_c2], [<BitsVal 8>, blockL40i0_40_58_c3]
  void call <Bits, 32bits, unsigned> @hls.write(o)
  br [label %blockL40i0_40 ]
blockL40i0_40_58_c1:
  br [label %blockL40i0_40_getSwEnd ]
blockL40i0_40_58_c2:
  br [label %blockL40i0_40_getSwEnd ]
blockL40i0_40_58_c3:
  br [label %blockL40i0_40_getSwEnd ]
}