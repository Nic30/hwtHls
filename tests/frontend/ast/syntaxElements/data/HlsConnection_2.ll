define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a2 = call <Bits, 32bits, unsigned> @hls.read(a)
  void call <Bits, 32bits, unsigned> @hls.write(a2)
  br [label %top_whC ]
}