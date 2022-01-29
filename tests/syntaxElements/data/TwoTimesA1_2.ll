define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a3 = call <Bits, 8bits> @hls.read(a)
  %4 = INDEX a3, <HSliceVal slice(<BitsVal 7>, <BitsVal 0>, <BitsVal -1>)>
  %5 = CONCAT %4, <BitsVal 0>
  void call <Bits, 8bits> @hls.write(%5)
  br [label %top_whC ]
}