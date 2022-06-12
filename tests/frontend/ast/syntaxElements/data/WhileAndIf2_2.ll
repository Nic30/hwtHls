define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh_wh ]
top_wh_wh:
  %5 = phi <Bits, 8bits> [<BitsVal 10>, top_whC], [%7, top_wh_wh]
  dataIn6 = call <Bits, 8bits> @hls.read(dataIn)
  %7 = SUB %5, dataIn6
  void call <Bits, 8bits> @hls.write(%7)
  %9 = EQ %7, <BitsVal 0>
  br [label %top_whC %9]
  [label %top_wh_wh ]
}