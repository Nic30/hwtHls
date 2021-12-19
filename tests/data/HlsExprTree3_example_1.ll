define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a_read = call <Bits, 32bits, unsigned> @hls.read(a)
  b_read = call <Bits, 32bits, unsigned> @hls.read(b)
  %3 = ADD a_read, b_read
  c_read = call <Bits, 32bits, unsigned> @hls.read(c)
  %4 = ADD %3, c_read
  d_read = call <Bits, 32bits, unsigned> @hls.read(d)
  %5 = MUL %4, d_read
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  x_read = call <Bits, 32bits, unsigned> @hls.read(x)
  y_read = call <Bits, 32bits, unsigned> @hls.read(y)
  %6 = ADD x_read, y_read
  z_read = call <Bits, 32bits, unsigned> @hls.read(z)
  %7 = MUL %6, z_read
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  %8 = ADD x_read, y_read
  w_read = call <Bits, 32bits, unsigned> @hls.read(w)
  %9 = MUL %8, w_read
  void call <Bits, 32bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}