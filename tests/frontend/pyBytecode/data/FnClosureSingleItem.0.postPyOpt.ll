define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL22i0_22 ]
blockL22i0_22:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  void call <Bits, 8bits, unsigned> @hls.write(<HlsRead i0 i, <Bits, 8bits, unsigned>>)
  br [label %blockL22i0_22 ]
}