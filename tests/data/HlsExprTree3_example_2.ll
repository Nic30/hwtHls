define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a = call <Bits, 32bits, unsigned> @hls.read(a)
  b = call <Bits, 32bits, unsigned> @hls.read(b)
  %10 = ADD b, a
  c = call <Bits, 32bits, unsigned> @hls.read(c)
  %11 = ADD %10, c
  d = call <Bits, 32bits, unsigned> @hls.read(d)
  %12 = MUL %11, d
  void call <Bits, 32bits> @hls.write(%12)
  x = call <Bits, 32bits, unsigned> @hls.read(x)
  y = call <Bits, 32bits, unsigned> @hls.read(y)
  %14 = ADD y, x
  z = call <Bits, 32bits, unsigned> @hls.read(z)
  %15 = MUL %14, z
  void call <Bits, 32bits> @hls.write(%15)
  w = call <Bits, 32bits, unsigned> @hls.read(w)
  %17 = MUL w, %14
  void call <Bits, 32bits> @hls.write(%17)
  br [label %top_whC ]
}