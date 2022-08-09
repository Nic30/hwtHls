define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat:
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_whC ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_whC:
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_wh ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_wh:
  a0 = call <Bits, 16bits, unsigned> @hls.read(a)
  %2 = CONCAT a0, <BitsVal 16>
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarConcat__HlsSlice2TmpHlsVarConcat_whC ]
}