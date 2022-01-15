define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  %2 = phi <Bits, 32bits, unsigned> [<BitsVal 0, mask 0>, top], [%6, top_wh]
  br [label %top_wh ]
top_wh:
  %3 = INDEX %2, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  %4 = CONCAT <BitsVal 16>, %3
  a0 = call <Bits, 16bits, unsigned> @hls.read(a)
  %5 = INDEX %4, <HSliceVal slice(<BitsVal 32>, <BitsVal 16>, <BitsVal -1>)>
  %6 = CONCAT %5, a0
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %top_whC ]
}