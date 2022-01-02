define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a = call <Bits, 16bits, unsigned> @hls.read(a)
  %5 = CONCAT <BitsVal 16>, a
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %top_whC ]
}