define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL32i0_32 ]
blockL32i0_32:
  i0 = call <Bits, 2bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 0>
  %2 = EQ i0, <BitsVal 1>
  %3 = EQ i0, <BitsVal 2>
  br [label %blockL32i0_32_48_c0 %1]
  [label %blockL32i0_32_48_c1 %2]
  [label %blockL32i0_32_48_c2 %3]
  [label %blockL32i0_32_48_c3 ]
blockL32i0_32_48_c0:
  br [label %blockL32i0_32_getSwEnd ]
blockL32i0_32_getSwEnd:
  %4 = phi <Bits, 32bits, unsigned> [<BitsVal 1>, blockL32i0_32_48_c0], [<BitsVal 2>, blockL32i0_32_48_c1], [<BitsVal 4>, blockL32i0_32_48_c2], [<BitsVal 8>, blockL32i0_32_48_c3]
  void call <Bits, 32bits, unsigned> @hls.write(o)
  br [label %blockL32i0_32 ]
blockL32i0_32_48_c1:
  br [label %blockL32i0_32_getSwEnd ]
blockL32i0_32_48_c2:
  br [label %blockL32i0_32_getSwEnd ]
blockL32i0_32_48_c3:
  br [label %blockL32i0_32_getSwEnd ]
}