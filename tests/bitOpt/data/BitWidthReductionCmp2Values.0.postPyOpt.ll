define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL10i0_10 ]
blockL10i0_10:
  i0 = call <Bits, 16bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 10>
  br [label %blockL10i0_34 %1]
  [label %blockL10i0_50 ]
blockL10i0_34:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 20>)
  br [label %blockL10i0_90 ]
blockL10i0_90:
  br [label %blockL10i0_10 ]
blockL10i0_50:
  %4 = EQ i0, <BitsVal 11>
  br [label %blockL10i0_60 %4]
  [label %blockL10i0_76 ]
blockL10i0_60:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 25>)
  br [label %blockL10i0_90 ]
blockL10i0_76:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 26>)
  br [label %blockL10i0_90 ]
}