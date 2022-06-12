define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a0 = call <Bits, 32bits, unsigned> @hls.read(a)
  %2 = INDEX a0, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  void call <Bits, 16bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}