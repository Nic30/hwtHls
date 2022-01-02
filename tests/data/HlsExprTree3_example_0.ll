define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a = call <Bits, 32bits, unsigned> @hls.read(a)
  b = call <Bits, 32bits, unsigned> @hls.read(b)
  %3 = ADD a, b
  c = call <Bits, 32bits, unsigned> @hls.read(c)
  %4 = ADD %3, c
  d = call <Bits, 32bits, unsigned> @hls.read(d)
  %5 = MUL %4, d
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  x = call <Bits, 32bits, unsigned> @hls.read(x)
  y = call <Bits, 32bits, unsigned> @hls.read(y)
  %6 = ADD x, y
  z = call <Bits, 32bits, unsigned> @hls.read(z)
  %7 = MUL %6, z
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  %8 = ADD x, y
  w = call <Bits, 32bits, unsigned> @hls.read(w)
  %9 = MUL %8, w
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}