define dso_local i32 @main() #0 {
mainThread:
  br [label %block26 ]
block26:
  i3 = call <Bits, 8bits, unsigned> @hls.read(i)
  void call <Bits, 8bits, unsigned> @hls.write(i3)
  br [label %block26 ]
}