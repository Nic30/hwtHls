define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  %1 = phi <Bits, 32bits, unsigned> [<BitsVal 0, mask 0>, top], [%5, top_wh]
  br [label %top_wh ]
top_wh:
  %2 = INDEX %1, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  %3 = CONCAT <BitsVal 16>, %2
  a_read = call <Bits, 16bits, unsigned> @hls.read(a)
  %4 = INDEX %3, <HSliceVal slice(<BitsVal 32>, <BitsVal 16>, <BitsVal -1>)>
  %5 = CONCAT %4, a_read
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %top_whC ]
}