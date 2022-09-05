define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL18i0_18 ]
blockL18i0_18:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %blockL18i0_18 ]
}