define dso_local i32 @main() #0 {
mainThread:
  br [label %block12 ]
block12:
  i2 = call <Bits, 8bits, unsigned> @hls.read(i)
  void call <Bits, 8bits, unsigned> @hls.write(i2)
  br [label %block12 ]
}