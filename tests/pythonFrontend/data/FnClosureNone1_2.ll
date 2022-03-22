define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  void call <Bits, 8bits> @hls.write(<BitsVal 10>)
  br [label %mainThread ]
}