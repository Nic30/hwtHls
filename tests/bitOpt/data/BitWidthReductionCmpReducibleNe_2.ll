define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  a40 = call <Bits, 8bits, unsigned> @hls.read(a)
  b41 = call <Bits, 8bits, unsigned> @hls.read(b)
  %42 = NE a40, b41
  void call <Bits, 1bit> @hls.write(%42)
  void call <Bits, 1bit> @hls.write(%42)
  %45 = NE a40, b41
  void call <Bits, 1bit> @hls.write(%45)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  %49 = NE a40, b41
  void call <Bits, 1bit> @hls.write(%49)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  br [label %block0 ]
}