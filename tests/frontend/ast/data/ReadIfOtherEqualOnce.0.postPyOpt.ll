define dso_local i32 @main() #0 {
t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce:
  br [label %t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfC ]
t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfC:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = EQ a0, <BitsVal 3>
  br [label %t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_If %2]
  [label %t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfE ]
t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_If:
  b1 = call <Bits, 8bits> @hls.read(b)
  br [label %t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfE ]
t0_HlsAstReadIfTc_test_ReadIfOtherEqualOnce_ll__ReadIfOtherEqualOnce_IfE:
}