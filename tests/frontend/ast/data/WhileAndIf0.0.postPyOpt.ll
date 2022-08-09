define dso_local i32 @main() #0 {
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_whC:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_whC:
  %1 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh], [%6, t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfE]
  %2 = NE %1, <BitsVal 0>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh %2]
  [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_whE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfC:
  %3 = LT %1, <BitsVal 3>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_If %3]
  [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_Else ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_If:
  %4 = SUB %1, <BitsVal 1>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfE:
  %6 = phi <Bits, 8bits, unsigned> [%4, t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_If], [%5, t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_Else]
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_Else:
  %5 = SUB %1, <BitsVal 3>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_wh_IfE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_wh_whE:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf0_ll__WhileAndIf0_whC ]
}