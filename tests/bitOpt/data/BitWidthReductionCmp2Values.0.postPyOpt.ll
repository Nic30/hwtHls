define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL10i0_10 ]
blockL10i0_10:
  i0 = call <Bits, 16bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 10>
  br [label %blockL10i0_32 %1]
  [label %blockL10i0_48 ]
blockL10i0_32:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 20>)
  br [label %blockL10i0_88 ]
blockL10i0_88:
  br [label %blockL10i0_10 ]
blockL10i0_48:
  %4 = EQ i0, <BitsVal 11>
  br [label %blockL10i0_58 %4]
  [label %blockL10i0_74 ]
blockL10i0_58:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 25>)
  br [label %blockL10i0_88 ]
blockL10i0_74:
  void call <Bits, 16bits, unsigned> @hls.write(<BitsVal 26>)
  br [label %blockL10i0_88 ]
}