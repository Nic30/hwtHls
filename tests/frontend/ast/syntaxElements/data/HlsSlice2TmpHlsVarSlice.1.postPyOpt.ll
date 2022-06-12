define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice:
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC:
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_wh ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_wh:
  a0 = call <Bits, 16bits, unsigned> @hls.read(a)
  %6 = CONCAT <BitsVal 16>, a0
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC ]
}