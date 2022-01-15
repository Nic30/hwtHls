define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  br [label %top_wh_IfC ]
top_wh_IfC:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = EQ a0, <BitsVal 3>
  br [label %top_wh_If %2]
  [label %top_wh_IfE ]
top_wh_If:
  b1 = call <Bits, 8bits> @hls.read(b)
  br [label %top_wh_IfE ]
top_wh_IfE:
  br [label %top_whC ]
}