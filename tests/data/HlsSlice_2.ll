define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a = call <Bits, 32bits, unsigned> @hls.read(a)
  %2 = INDEX a, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  void call <Bits, 16bits> @hls.write(%2)
  br [label %top_whC ]
}