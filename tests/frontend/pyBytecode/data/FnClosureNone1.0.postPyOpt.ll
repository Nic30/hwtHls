define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL10i0_10 ]
blockL10i0_10:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %blockL10i0_10 ]
}