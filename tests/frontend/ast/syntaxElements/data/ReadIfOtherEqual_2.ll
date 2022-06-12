define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a3 = call <Bits, 8bits> @hls.read(a)
  %4 = EQ a3, <BitsVal 3>
  br [label %top_wh_If %4]
  [label %top_wh_IfE ]
top_wh_If:
  b5 = call <Bits, 8bits> @hls.read(b)
  br [label %top_wh_IfE ]
top_wh_IfE:
  br [label %top_whC ]
}