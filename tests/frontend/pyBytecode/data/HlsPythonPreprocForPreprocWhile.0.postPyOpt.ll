define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL8i0_8 ]
blockL8i0_8:
  br [label %blockL8i0_10 ]
blockL8i0_10:
  br [label %blockL8i0_L20i0_20 ]
blockL8i0_L20i0_20:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 0>)
  br [label %blockL8i0_L20i0_20 ]
}