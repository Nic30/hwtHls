define dso_local i32 @main() #0 {
mainThread:
  i3 = call <Bits, 8bits, unsigned> @hls.read(i)
  %4 = EQ i3, <BitsVal 2>
  br [label %block22 %4]
  [label %block36 ]
block22:
  void call <Bits, 8bits> @hls.write(<BitsVal 3>)
  br [label %block36 ]
block36:
}