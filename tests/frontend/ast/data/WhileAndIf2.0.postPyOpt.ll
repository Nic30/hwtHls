define dso_local i32 @main() #0 {
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_whC:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh ]
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_whC:
  %2 = phi <Bits, 8bits, unsigned> [<BitsVal 10>, t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh], [%4, t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_wh]
  %3 = NE %2, <BitsVal 0>
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_wh %3]
  [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_whE ]
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_wh:
  dataIn0 = call <Bits, 8bits, unsigned> @hls.read(dataIn)
  %4 = SUB %2, dataIn0
  void call <Bits, 8bits, unsigned> @hls.write(x)
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_whC ]
t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_wh_whE:
  br [label %t0_HlsAstWhileIf_TC_test_WhileAndIf2_ll__WhileAndIf2_whC ]
}