define dso_local i32 @main() #0 {
mainThread:
  br [label %block20 ]
block20:
  void call <Bits, 8bits> @hls.write(<BitsVal 0>)
  br [label %block20 ]
}