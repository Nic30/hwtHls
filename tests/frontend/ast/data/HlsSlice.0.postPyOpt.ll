define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_slice__HlsSlice:
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_whC ]
t0_HlsSlicingTC_test_slice__HlsSlice_whC:
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_wh ]
t0_HlsSlicingTC_test_slice__HlsSlice_wh:
  a0 = call <Bits, 32bits, unsigned> @hls.read(a)
  %2 = INDEX a0, <HSliceVal slice(16, 0, -1)>
  void call <Bits, 16bits, unsigned> @hls.write("<HlsRead a0 a, <Bits, 32bits, unsigned>>"[16:0])
  br [label %t0_HlsSlicingTC_test_slice__HlsSlice_whC ]
}