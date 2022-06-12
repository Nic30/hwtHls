define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice:
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC:
  %2 = phi <Bits, 32bits, unsigned> [<BitsVal 0, mask 0>, t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice], [%6, t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_wh]
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_wh ]
t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_wh:
  %3 = INDEX %2, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  %4 = CONCAT <BitsVal 16>, %3
  a0 = call <Bits, 16bits, unsigned> @hls.read(a)
  %5 = INDEX %4, <HSliceVal slice(<BitsVal 32>, <BitsVal 16>, <BitsVal -1>)>
  %6 = CONCAT %5, a0
  void call <Bits, 32bits, unsigned> @hls.write(tmp)
  br [label %t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC ]
}