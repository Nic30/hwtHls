define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = ADD a0, a0
  void call <Bits, 8bits, unsigned> @hls.write(sig_)
  br [label %top_whC ]
}