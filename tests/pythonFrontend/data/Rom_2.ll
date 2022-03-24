define dso_local i32 @main() #0 {
mainThread:
  br [label %block18 ]
block18:
  i6 = call <Bits, 2bits, unsigned> @hls.read(i)
  %7 = EQ i6, <BitsVal 0>
  %8 = EQ i6, <BitsVal 1>
  %9 = EQ i6, <BitsVal 2>
  br [label %block28_getSwEnd %7]
  [label %block28_getSwEnd.fold.split %8]
  [label %block28_getSwEnd.fold.split3 %9]
  [label %block28_44_c3 ]
block28_getSwEnd:
  %10 = phi <Bits, 32bits> [<BitsVal 8>, block28_44_c3], [<BitsVal 1>, block18], [<BitsVal 2>, block28_getSwEnd.fold.split], [<BitsVal 4>, block28_getSwEnd.fold.split3]
  void call <Bits, 32bits> @hls.write(%10)
  br [label %block18 ]
block28_getSwEnd.fold.split:
  br [label %block28_getSwEnd ]
block28_getSwEnd.fold.split3:
  br [label %block28_getSwEnd ]
block28_44_c3:
  br [label %block28_getSwEnd ]
}