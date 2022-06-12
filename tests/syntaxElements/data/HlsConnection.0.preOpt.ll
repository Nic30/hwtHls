define dso_local i32 @main() #0 {
t0_HlsSlicingTC_test_connection__HlsConnection:
  br [label %t0_HlsSlicingTC_test_connection__HlsConnection_whC ]
t0_HlsSlicingTC_test_connection__HlsConnection_whC:
  br [label %t0_HlsSlicingTC_test_connection__HlsConnection_wh ]
t0_HlsSlicingTC_test_connection__HlsConnection_wh:
  a0 = call <Bits, 32bits, unsigned> @hls.read(a)
  void call <Bits, 32bits, unsigned> @hls.write(a0)
  br [label %t0_HlsSlicingTC_test_connection__HlsConnection_whC ]
}