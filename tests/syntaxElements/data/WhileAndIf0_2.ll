define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh_wh_IfC ]
top_wh_wh_IfC:
  %7 = phi <Bits, 8bits> [<BitsVal 10>, top_whC], [%10, top_wh_wh_IfC]
  %8 = LT %7, <BitsVal 3>
  %9 = TERNARY %8, <BitsVal 1>, <BitsVal 3>
  %10 = SUB %7, %9
  void call <Bits, 8bits> @hls.write(%10)
  %12 = NE %10, <BitsVal 0>
  br [label %top_wh_wh_IfC %12]
  [label %top_whC ]
}