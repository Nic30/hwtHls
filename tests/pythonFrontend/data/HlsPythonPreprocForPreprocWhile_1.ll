define dso_local i32 @main() #0 {
mainThread:
  br [label %block8 ]
block8:
  br [label %block10 ]
block10:
  br [label %block12 ]
block12:
  br [label %block20 ]
block20:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 0>)
  br [label %block12 ]
}