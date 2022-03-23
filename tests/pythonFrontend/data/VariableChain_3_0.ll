define dso_local i32 @main() #0 {
mainThread:
  br [label %block26 ]
block26:
  br [label %block36 ]
block36:
  br [label %block44 ]
block44:
  br [label %block44i0_46 ]
block44i0_46:
  br [label %block44i0_60 ]
block44i0_60:
  i0 = call <Bits, 8bits, unsigned> @hls.read(i)
  br [label %block44i0_86 ]
block44i0_86:
  br [label %block44i1_44 ]
block44i1_44:
  br [label %block44i1_46 ]
block44i1_46:
  br [label %block44i1_74 ]
block44i1_74:
  br [label %block44i1_86 ]
block44i1_86:
  br [label %block44i2_44 ]
block44i2_44:
  br [label %block44i2_46 ]
block44i2_46:
  br [label %block44i2_74 ]
block44i2_74:
  br [label %block44i2_86 ]
block44i2_86:
  br [label %block44i3_44 ]
block44i3_44:
  br [label %block96 ]
block96:
  void call <Bits, 8bits, unsigned> @hls.write(i2)
  br [label %block26 ]
}