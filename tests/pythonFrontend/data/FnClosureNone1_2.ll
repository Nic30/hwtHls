define dso_local i32 @main() #0 {
mainThread:
  br [label %mainThread_0 ]
mainThread_0:
  void call <Bits, 8bits> @hls.write(<BitsVal 10>)
  br [label %mainThread_0 ]
}