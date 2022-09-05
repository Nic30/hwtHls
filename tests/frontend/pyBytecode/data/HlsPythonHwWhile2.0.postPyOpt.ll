define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL20i0_20 ]
blockL20i0_20:
  %0 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, block0], [%5, blockL20i0_56]
  %1 = LE %0, <BitsVal 4>
  br [label %blockL20i0_28 %1]
  [label %blockL20i0_44 ]
blockL20i0_28:
  void call <Bits, 8bits, unsigned> @hls.write(i)
  br [label %blockL20i0_56 ]
blockL20i0_56:
  %5 = ADD %0, <BitsVal 1>
  br [label %blockL20i0_20 ]
blockL20i0_44:
  %7 = EQ %0, <BitsVal 10>
  br [label %block54 %7]
  [label %blockL20i0_56 ]
block54:
  br [label %block74 ]
block74:
  br [label %blockL84i0_84 ]
blockL84i0_84:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 0>)
  br [label %blockL84i0_84 ]
}