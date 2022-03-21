define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  a41 = call <Bits, 8bits, unsigned> @hls.read(a)
  b42 = call <Bits, 8bits, unsigned> @hls.read(b)
  %43 = NE a41, b42
  void call <Bits, 1bit> @hls.write(%43)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  void call <Bits, 1bit> @hls.write(%43)
  %47 = NE a41, b42
  void call <Bits, 1bit> @hls.write(%47)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  %51 = NE a41, b42
  void call <Bits, 1bit> @hls.write(%51)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  br [label %mainThread ]
}