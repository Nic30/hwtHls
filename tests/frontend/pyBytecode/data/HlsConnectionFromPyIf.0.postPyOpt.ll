define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 2>
  br [label %block24 %1]
  [label %block42 ]
block24:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 3>)
block42:
}