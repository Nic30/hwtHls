define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  br [label %block10 ]
block10:
  void call <Bits, 8bits, unsigned> @hls.write(<BitsVal 10>)
  br [label %mainThread ]
}