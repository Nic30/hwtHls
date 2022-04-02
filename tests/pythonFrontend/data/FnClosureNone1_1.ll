define dso_local i32 @main() #0 {
mainThread:
  br [label %mainThread_0 ]
mainThread_0:
  br [label %block10 ]
block10:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %mainThread_0 ]
}