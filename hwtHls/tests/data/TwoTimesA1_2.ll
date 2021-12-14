define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a_read = call <Bits, 8bits> @hls.read(a)
  %2 = MUL a_read, <BitsVal 2>
  void call <Bits, 8bits> @hls.write(%2)
  br [label %top_whC ]
}