define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a = call <Bits, 16bits, unsigned> @hls.read(a)
  %2 = CONCAT <BitsVal 16>, a
  void call <Bits, 32bits> @hls.write(%2)
  br [label %top_whC ]
}