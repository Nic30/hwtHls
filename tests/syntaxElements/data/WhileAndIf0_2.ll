define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh_wh_IfC ]
top_wh_wh_IfC:
  %7 = phi <Bits, 8bits> [<BitsVal 10>, top_whC], [%11, top_wh_wh_IfC]
  %8 = LT %7, <BitsVal 3>
  %9 = CONCAT %8, <BitsVal 1>
  %10 = CONCAT <BitsVal 63>, %9
  %11 = ADD %10, %7
  void call <Bits, 8bits> @hls.write(%11)
  %13 = EQ %11, <BitsVal 0>
  br [label %top_whC %13]
  [label %top_wh_wh_IfC ]
}