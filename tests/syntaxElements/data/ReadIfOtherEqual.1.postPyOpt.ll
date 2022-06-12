define dso_local i32 @main() #0 {
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual:
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_whC ]
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_whC:
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh ]
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh:
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_IfC ]
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_IfC:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = EQ a0, <BitsVal 3>
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_If %2]
  [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_IfE ]
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_If:
  b1 = call <Bits, 8bits> @hls.read(b)
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_IfE ]
t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_wh_IfE:
  br [label %t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_whC ]
}