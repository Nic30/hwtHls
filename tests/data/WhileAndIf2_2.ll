define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh_wh ]
top_wh_wh:
  %4 = phi <Bits, 8bits> [<BitsVal 10>, top_whC], [%5, top_wh_wh]
  dataIn = call <Bits, 8bits, unsigned> @hls.read(dataIn)
  %5 = SUB %4, dataIn
  void call <Bits, 8bits> @hls.write(%5)
  %7 = NE %5, <BitsVal 0>
  br [label %top_wh_wh %7]
  [label %top_whC ]
}