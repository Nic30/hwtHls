define dso_local i32 @main() #0 {
mainThread:
  br [label %block12 ]
block12:
  br [label %block22 ]
block22:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  void call <Bits, 8bits, unsigned> @hls.write(i0)
  br [label %block12 ]
}