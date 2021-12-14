define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  br [label %top_wh_whC ]
top_wh_whC:
  %1 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, top_wh], [%3, top_wh_wh]
  %2 = NE %1, <BitsVal 0>
  br [label %top_wh_wh %2]
  [label %top_wh_whE ]
top_wh_wh:
  dataIn_read = call <Bits, 8bits, unsigned> @hls.read(dataIn)
  %3 = SUB %1, dataIn_read
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %top_wh_whC ]
top_wh_whE:
  br [label %top_whC ]
}