define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a_read = call <Bits, 32bits, unsigned> @hls.read(a)
  %1 = INDEX a_read, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  void call <Bits, 16bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}