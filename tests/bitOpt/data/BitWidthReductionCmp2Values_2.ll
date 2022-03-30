define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  i7 = call <Bits, 16bits, unsigned> @hls.read(i)
  %8 = NE i7, <BitsVal 11>
  %9 = EQ i7, <BitsVal 11>
  %10 = EQ i7, <BitsVal 10>
  %11 = CONCAT %8, %9
  %12 = CONCAT <BitsVal 2>, %11
  %13 = TERNARY %10, <BitsVal 4>, %12
  %14 = CONCAT <BitsVal 1>, %13
  void call <Bits, 16bits> @hls.write(%14)
  br [label %mainThread ]
}