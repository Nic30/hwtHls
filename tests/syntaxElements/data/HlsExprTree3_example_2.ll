define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a18 = call <Bits, 32bits, unsigned> @hls.read(a)
  b19 = call <Bits, 32bits, unsigned> @hls.read(b)
  %20 = ADD b19, a18
  c21 = call <Bits, 32bits, unsigned> @hls.read(c)
  %22 = ADD %20, c21
  d23 = call <Bits, 32bits, unsigned> @hls.read(d)
  %24 = MUL %22, d23
  void call <Bits, 32bits> @hls.write(%24)
  x26 = call <Bits, 32bits, unsigned> @hls.read(x)
  y27 = call <Bits, 32bits, unsigned> @hls.read(y)
  %28 = ADD y27, x26
  z29 = call <Bits, 32bits, unsigned> @hls.read(z)
  %30 = MUL %28, z29
  void call <Bits, 32bits> @hls.write(%30)
  w32 = call <Bits, 32bits, unsigned> @hls.read(w)
  %33 = MUL w32, %28
  void call <Bits, 32bits> @hls.write(%33)
  br [label %top_whC ]
}