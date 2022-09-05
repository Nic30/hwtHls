define dso_local i32 @main() #0 {
t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0:
  br [label %t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0_whC ]
t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0_whC:
  br [label %t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0_wh ]
t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0_wh:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = ADD a0, a0
  void call <Bits, 8bits, unsigned> @hls.write(a._reinterpret_cast(Bits(8, signed=False)) + a._reinterpret_cast(Bits(8, signed=False)))
  br [label %t0_TwoTimesA_TC_test_TwoTimesA0__TwoTimesA0_whC ]
}