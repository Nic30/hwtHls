define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a_read = call <Bits, 8bits> @hls.read(a)
  %1 = ADD a_read, a_read
  void call <Bits, 8bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}