define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  a_read = call <Bits, 8bits> @hls.read(a)
  %1 = EQ a_read, <BitsVal 3>
  br [label %top_wh_If %1]
  [label %top_wh_IfE ]
top_wh_If:
  b_read = call <Bits, 8bits> @hls.read(b)
  br [label %top_wh_IfE ]
top_wh_IfE:
  br [label %top_whC ]
}