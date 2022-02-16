define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  a40 = call <Bits, 8bits, unsigned> @hls.read(a)
  b41 = call <Bits, 8bits, unsigned> @hls.read(b)
  %42 = EQ a40, b41
  void call <Bits, 1bit> @hls.write(%42)
  void call <Bits, 1bit> @hls.write(%42)
  %45 = EQ a40, b41
  void call <Bits, 1bit> @hls.write(%45)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  %49 = EQ a40, b41
  void call <Bits, 1bit> @hls.write(%49)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  br [label %block0 ]
}