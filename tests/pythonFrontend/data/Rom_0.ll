define dso_local i32 @main() #0 {
mainThread:
  br [label %block18 ]
block18:
  br [label %block28 ]
block28:
  i0 = call <Bits, 2bits, unsigned> @hls.read(i)
  %1 = EQ i0, <BitsVal 0>
  %2 = EQ i0, <BitsVal 1>
  %3 = EQ i0, <BitsVal 2>
  br [label %block28_44_c0 %1]
  [label %block28_44_c1 %2]
  [label %block28_44_c2 %3]
  [label %block28_44_c3 ]
block28_44_c0:
  br [label %block28_getSwEnd ]
block28_getSwEnd:
  %4 = phi <Bits, 32bits, unsigned> [<BitsVal 1>, block28_44_c0], [<BitsVal 2>, block28_44_c1], [<BitsVal 4>, block28_44_c2], [<BitsVal 8>, block28_44_c3]
  void call <Bits, 32bits, unsigned> @hls.write(o)
  br [label %block18 ]
block28_44_c1:
  br [label %block28_getSwEnd ]
block28_44_c2:
  br [label %block28_getSwEnd ]
block28_44_c3:
  br [label %block28_getSwEnd ]
}