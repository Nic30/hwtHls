define dso_local i32 @main() #0 {
mainThread:
  br [label %block8 ]
block8:
  br [label %block18 ]
block18:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %block8 ]
}