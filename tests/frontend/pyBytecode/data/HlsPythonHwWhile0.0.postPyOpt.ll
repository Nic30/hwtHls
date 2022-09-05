define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL20i0_20 ]
blockL20i0_20:
  %0 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, block0], [%4, blockL20i0_58]
  %1 = ADD %0, <BitsVal 1>
  void call <Bits, 8bits, unsigned> @hls.write(i)
  i_rst3 = call <Bits, 1bit> @hls.read(i_rst)
  br [label %blockL20i0_54 i_rst3]
  [label %blockL20i0_58 ]
blockL20i0_54:
  br [label %blockL20i0_58 ]
blockL20i0_58:
  %4 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, blockL20i0_54], [%1, blockL20i0_20]
  br [label %blockL20i0_20 ]
}