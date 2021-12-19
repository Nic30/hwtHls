define dso_local i32 @main() #0 {
top:
  br [label %top_whC ]
top_whC:
  br [label %top_wh ]
top_wh:
  a_read = call <Bits, 32bits, unsigned> @hls.read(a)
  void call <Bits, 32bits, unsigned> @hls.write(a_read)
  br [label %top_whC ]
}