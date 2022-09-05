define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 2>
  br [label %block22 %1]
  [label %block40 ]
block22:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 3>)
block40:
  %4 = EQ i0, <BitsVal 10>
  br [label %block50 %4]
  [label %block68 ]
block50:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 11>)
block68:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
}