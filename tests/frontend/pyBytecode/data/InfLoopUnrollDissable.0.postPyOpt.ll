define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL20i0_20 ]
blockL20i0_20:
  %1 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, mainThread], [%2, blockL20i0_20]
  void call <Bits, 8bits, unsigned> @hls.write(i)
  %2 = ADD %1, <BitsVal 1>
  br [label %blockL20i0_20 ]
}