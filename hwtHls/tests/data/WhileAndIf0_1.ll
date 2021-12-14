define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  br [label %top_wh_whC ]
top_wh_whC:
  %1 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, top_wh], [%6, top_wh_wh_IfE]
  %2 = NE %1, <BitsVal 0>
  br [label %top_wh_wh %2]
  [label %top_wh_whE ]
top_wh_wh:
  br [label %top_wh_wh_IfC ]
top_wh_wh_IfC:
  %3 = LT %1, <BitsVal 3>
  br [label %top_wh_wh_If %3]
  [label %top_wh_wh_Else ]
top_wh_wh_If:
  %4 = SUB %1, <BitsVal 1>
  br [label %top_wh_wh_IfE ]
top_wh_wh_IfE:
  %6 = phi <Bits, 8bits, unsigned> [%4, top_wh_wh_If], [%5, top_wh_wh_Else]
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %top_wh_whC ]
top_wh_wh_Else:
  %5 = SUB %1, <BitsVal 3>
  br [label %top_wh_wh_IfE ]
top_wh_whE:
  br [label %top_whC ]
}