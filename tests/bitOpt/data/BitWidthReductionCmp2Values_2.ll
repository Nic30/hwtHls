define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  i6 = call <Bits, 16bits, unsigned> @hls.read(i)
  %7 = NE i6, <BitsVal 11>
  %8 = EQ i6, <BitsVal 11>
  %9 = EQ i6, <BitsVal 10>
  %10 = CONCAT %7, %8
  %11 = CONCAT <BitsVal 2>, %10
  %12 = TERNARY %9, <BitsVal 4>, %11
  %13 = CONCAT <BitsVal 1>, %12
  void call <Bits, 16bits> @hls.write(%13)
  br [label %mainThread ]
}