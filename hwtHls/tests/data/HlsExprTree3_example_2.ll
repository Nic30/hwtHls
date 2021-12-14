define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a_read = call <Bits, 32bits, unsigned> @hls.read(a)
  b_read = call <Bits, 32bits, unsigned> @hls.read(b)
  %10 = ADD b_read, a_read
  c_read = call <Bits, 32bits, unsigned> @hls.read(c)
  %11 = ADD %10, c_read
  d_read = call <Bits, 32bits, unsigned> @hls.read(d)
  %12 = MUL %11, d_read
  void call <Bits, 32bits> @hls.write(%12)
  x_read = call <Bits, 32bits, unsigned> @hls.read(x)
  y_read = call <Bits, 32bits, unsigned> @hls.read(y)
  %14 = ADD y_read, x_read
  z_read = call <Bits, 32bits, unsigned> @hls.read(z)
  %15 = MUL %14, z_read
  void call <Bits, 32bits> @hls.write(%15)
  w_read = call <Bits, 32bits, unsigned> @hls.read(w)
  %17 = MUL w_read, %14
  void call <Bits, 32bits> @hls.write(%17)
  br [label %top_whC ]
}