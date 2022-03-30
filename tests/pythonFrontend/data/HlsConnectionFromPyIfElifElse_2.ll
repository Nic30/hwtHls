define dso_local i32 @main() #0 {
mainThread:
  i7 = call <Bits, 8bits, unsigned> @hls.read(i)
  %8 = EQ i7, <BitsVal 10>
  %9 = EQ i7, <BitsVal 2>
  %10 = CONCAT <BitsVal 1>, %8
  %11 = TERNARY %9, <BitsVal 1>, %10
  %12 = INDEX %11, <BitsVal 0>
  %13 = INDEX %11, <BitsVal 0>
  %14 = CONCAT <BitsVal 1>, %12
  %15 = CONCAT %13, %14
  %16 = CONCAT <BitsVal 0>, %15
  void call <Bits, 8bits> @hls.write(%16)
}