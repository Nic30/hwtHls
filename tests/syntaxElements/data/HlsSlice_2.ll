define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a3 = call <Bits, 32bits, unsigned> @hls.read(a)
  %4 = INDEX a3, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  void call <Bits, 16bits> @hls.write(%4)
  br [label %top_whC ]
}