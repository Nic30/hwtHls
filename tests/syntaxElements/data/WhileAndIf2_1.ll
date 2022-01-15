define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  br [label %top_wh_whC ]
top_wh_whC:
  %2 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, top_wh], [%4, top_wh_wh]
  %3 = NE %2, <BitsVal 0>
  br [label %top_wh_wh %3]
  [label %top_wh_whE ]
top_wh_wh:
  dataIn0 = call <Bits, 8bits, unsigned> @hls.read(dataIn)
  %4 = SUB %2, dataIn0
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %top_wh_whC ]
top_wh_whE:
  br [label %top_whC ]
}