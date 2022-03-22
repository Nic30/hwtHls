define dso_local i32 @main() #0 {
mainThread:
  br [label %block4 ]
block4:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 2>
  br [label %block26 %1]
  [label %block42 ]
block26:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 3>)
  br [label %block84 ]
block84:
block42:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %block84 ]
}