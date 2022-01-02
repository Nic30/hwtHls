define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a = call <Bits, 16bits, unsigned> @hls.read(a)
  %7 = CONCAT <BitsVal 16>, a
  void call <Bits, 32bits> @hls.write(%7)
  br [label %top_whC ]
}