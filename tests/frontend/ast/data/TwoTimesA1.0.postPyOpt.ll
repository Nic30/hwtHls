define dso_local i32 @main() #0 {
t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1:
  br [label %t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_whC ]
t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_whC:
  br [label %t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_wh ]
t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_wh:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = ADD a0, a0
  void call <Bits, 8bits, unsigned> @hls.write(sig_)
  br [label %t0_TwoTimesA_TC_test_TwoTimesA1__TwoTimesA1_whC ]
}