define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a3 = call <Bits, 16bits, unsigned> @hls.read(a)
  %4 = CONCAT <BitsVal 16>, a3
  void call <Bits, 32bits> @hls.write(%4)
  br [label %top_whC ]
}