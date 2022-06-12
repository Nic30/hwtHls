define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_slice__HlsSlice:
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_whC ]
t0_HlsSlicingTC_test_slice__HlsSlice_whC:
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_wh ]
t0_HlsSlicingTC_test_slice__HlsSlice_wh:
  a0 = call <Bits, 32bits, unsigned> @hls.read(a)
  %2 = INDEX a0, <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>
  void call <Bits, 16bits, unsigned> @hls.write(sig_)
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_whC ]
}