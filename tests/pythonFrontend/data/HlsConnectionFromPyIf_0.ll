define dso_local i32 @main() #0 {
mainThread:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 2>
  br [label %block22 %1]
  [label %block36 ]
block22:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 3>)
  br [label %block36 ]
block36:
}