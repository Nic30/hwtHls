define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL36i0_36 ]
blockL36i0_36:
  br [label %blockL36i0_L44i0_44 ]
blockL36i0_L44i0_44:
  br [label %blockL36i0_L44i0_46 ]
blockL36i0_L44i0_46:
  br [label %blockL36i0_L44i0_60 ]
blockL36i0_L44i0_60:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  br [label %blockL36i0_L44i0_86 ]
blockL36i0_L44i0_86:
  br [label %blockL36i0_L44i1_44 ]
blockL36i0_L44i1_44:
  br [label %blockL36i0_96 ]
blockL36i0_96:
  void call <Bits, 8bits, unsigned> @hls.write(i0)
  br [label %blockL36i0_36 ]
}