define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a3 = call <Bits, 8bits> @hls.read(a)
  %4 = MUL a3, <BitsVal 2>
  void call <Bits, 8bits> @hls.write(%4)
  br [label %top_whC ]
}