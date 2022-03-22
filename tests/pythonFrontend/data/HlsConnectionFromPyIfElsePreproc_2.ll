define dso_local i32 @main() #0 {
mainThread:
  i4 = call <Bits, 8bits, unsigned> @hls.read(i)
  %5 = EQ i4, <BitsVal 2>
  %6 = NOT %5
  %7 = CONCAT <BitsVal 1>, %5
  %8 = CONCAT %6, %7
  %9 = CONCAT <BitsVal 0>, %8
  void call <Bits, 8bits> @hls.write(%9)
}