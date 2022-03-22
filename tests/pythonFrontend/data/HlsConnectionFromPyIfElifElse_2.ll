define dso_local i32 @main() #0 {
mainThread:
  i6 = call <Bits, 8bits, unsigned> @hls.read(i)
  %7 = EQ i6, <BitsVal 10>
  %8 = EQ i6, <BitsVal 2>
  %9 = CONCAT <BitsVal 1>, %7
  %10 = TERNARY %8, <BitsVal 1>, %9
  %11 = INDEX %10, <BitsVal 0>
  %12 = INDEX %10, <BitsVal 0>
  %13 = CONCAT <BitsVal 1>, %11
  %14 = CONCAT %12, %13
  %15 = CONCAT <BitsVal 0>, %14
  void call <Bits, 8bits> @hls.write(%15)
}