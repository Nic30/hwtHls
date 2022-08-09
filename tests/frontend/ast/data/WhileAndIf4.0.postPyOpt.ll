define dso_local i32 @main() #0 {
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_whC:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_whC:
  %2 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh], [%3, t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfE]
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh:
  dataIn0 = call <Bits, 8bits, unsigned> @hls.read(dataIn)
  %3 = SUB %2, dataIn0
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfC:
  %4 = LT %3, <BitsVal 5>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_If %4]
  [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_If:
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_wh_IfE:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf4_ll__WhileAndIf4_wh_whC ]
}