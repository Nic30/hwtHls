define dso_local i32 @main() #0 {
t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example:
  br [label %t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_whC ]
t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_whC:
  br [label %t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_wh ]
t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_wh:
  a0 = call <Bits, 32bits, unsigned> @hls.read(a)
  b1 = call <Bits, 32bits, unsigned> @hls.read(b)
  c2 = call <Bits, 32bits, unsigned> @hls.read(c)
  d3 = call <Bits, 32bits, unsigned> @hls.read(d)
  %11 = ADD a0, b1
  %12 = ADD %11, c2
  %13 = MUL %12, d3
  void call <Bits, 32bits, unsigned> @hls.write(("<HlsRead a0 a, <Bits, 32bits, unsigned>>" + "<HlsRead b1 b, <Bits, 32bits, unsigned>>" + "<HlsRead c2 c, <Bits, 32bits, unsigned>>") * "<HlsRead d3 d, <Bits, 32bits, unsigned>>")
  x4 = call <Bits, 32bits, unsigned> @hls.read(x)
  y5 = call <Bits, 32bits, unsigned> @hls.read(y)
  %14 = ADD x4, y5
  z6 = call <Bits, 32bits, unsigned> @hls.read(z)
  %15 = MUL %14, z6
  void call <Bits, 32bits, unsigned> @hls.write(("<HlsRead x4 x, <Bits, 32bits, unsigned>>" + "<HlsRead y5 y, <Bits, 32bits, unsigned>>") * "<HlsRead z6 z, <Bits, 32bits, unsigned>>")
  %16 = ADD x4, y5
  w7 = call <Bits, 32bits, unsigned> @hls.read(w)
  %17 = MUL %16, w7
  void call <Bits, 32bits, unsigned> @hls.write(("<HlsRead x4 x, <Bits, 32bits, unsigned>>" + "<HlsRead y5 y, <Bits, 32bits, unsigned>>") * "<HlsRead w7 w, <Bits, 32bits, unsigned>>")
  br [label %t0_HlsAstExprTree3_example_TC_test_ll__HlsAstExprTree3_example_whC ]
}