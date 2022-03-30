define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  br [label %block10 ]
block10:
  i0 = call <Bits, 16bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 10>
  br [label %block32 %1]
  [label %block48 ]
block32:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 20>)
  br [label %mainThread ]
block48:
  %4 = EQ i0, <BitsVal 11>
  br [label %block58 %4]
  [label %block74 ]
block58:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 25>)
  br [label %mainThread ]
block74:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 26>)
  br [label %mainThread ]
}