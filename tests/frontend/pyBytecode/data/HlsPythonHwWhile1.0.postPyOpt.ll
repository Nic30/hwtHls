define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL20i0_20 ]
blockL20i0_20:
  %4 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, block0], [<BitsVal 0>, blockL20i0_62]
  br [label %blockL20i0_L22i0_22 ]
blockL20i0_L22i0_22:
  %1 = phi <Bits, 8bits, unsigned> [%4, blockL20i0_20], [%2, blockL20i0_L22i0_60]
  void call <Bits, 8bits, unsigned> @hls.write(i)
  %2 = ADD %1, <BitsVal 1>
  i_rst3 = call <Bits, 1bit> @hls.read(i_rst)
  br [label %blockL20i0_58 i_rst3]
  [label %blockL20i0_L22i0_60 ]
blockL20i0_58:
  br [label %blockL20i0_62 ]
blockL20i0_62:
  br [label %blockL20i0_20 ]
blockL20i0_L22i0_60:
  br [label %blockL20i0_L22i0_22 ]
}