define dso_local i32 @main() #0 {
mainThread:
  void call <Bits, 8bits> @hls.write(<BitsVal 0>)
  void call <Bits, 8bits> @hls.write(<BitsVal 1>)
  void call <Bits, 8bits> @hls.write(<BitsVal 2>)
  void call <Bits, 8bits> @hls.write(<BitsVal 3>)
}