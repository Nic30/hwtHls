define dso_local i32 @main() #0 {
mainThread:
  br [label %blockL30i0_30 ]
blockL30i0_30:
  %1 = phi <Bits, 8bits, unsigned> [<BitsVal 0>, mainThread], [%3, blockL30i0_30]
  %3 = phi <Bits, 8bits, unsigned> [<BitsVal 1>, mainThread], [%1, blockL30i0_30]
  void call <Bits, 8bits, unsigned> @hls.write(i0)
  void call <Bits, 8bits, unsigned> @hls.write(i1)
  br [label %blockL30i0_30 ]
}