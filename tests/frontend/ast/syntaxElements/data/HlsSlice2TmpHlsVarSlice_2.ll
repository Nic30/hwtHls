define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a8 = call <Bits, 16bits, unsigned> @hls.read(a)
  %9 = CONCAT <BitsVal 16>, a8
  void call <Bits, 32bits> @hls.write(%9)
  br [label %top_whC ]
}