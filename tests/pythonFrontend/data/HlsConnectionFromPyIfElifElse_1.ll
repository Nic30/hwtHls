define dso_local i32 @main() #0 {
mainThread:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 2>
  br [label %block22 %1]
  [label %block38 ]
block22:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 3>)
  br [label %block78 ]
block78:
block38:
  %3 = EQ i0, <BitsVal 10>
  br [label %block48 %3]
  [label %block64 ]
block48:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 11>)
  br [label %block78 ]
block64:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %block78 ]
}