define dso_local i32 @main() #0 {
mainThread:
  br [label %block12 ]
block12:
  void call <Bits, 8bits> @hls.write(<BitsVal 0>)
  br [label %block12 ]
}