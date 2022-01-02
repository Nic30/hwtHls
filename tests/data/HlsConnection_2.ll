define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a = call <Bits, 32bits, unsigned> @hls.read(a)
  void call <Bits, 32bits, unsigned> @hls.write(a)
  br [label %top_whC ]
}