define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  i0 = call <Bits, 16bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 10>
  br [label %block22 %1]
  [label %block38 ]
block22:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 20>)
  br [label %block0 ]
block38:
  %3 = EQ i0, <BitsVal 11>
  br [label %block48 %3]
  [label %block64 ]
block48:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 25>)
  br [label %block0 ]
block64:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 26>)
  br [label %block0 ]
}