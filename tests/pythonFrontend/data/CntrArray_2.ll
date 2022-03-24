define dso_local i32 @main() #0 {
mainThread:
  br [label %block40 ]
block40:
  %35 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%54, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %36 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%55, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %37 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%56, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %38 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%57, block50_getSwEnd_getSwEnd_106_setSwEnd]
  o_addr39 = call <Bits, 2bits, unsigned> @hls.read(o_addr)
  %40 = EQ o_addr39, <BitsVal 0>
  %41 = EQ o_addr39, <BitsVal 1>
  %42 = EQ o_addr39, <BitsVal 2>
  br [label %block50_getSwEnd %40]
  [label %block50_getSwEnd.fold.split %41]
  [label %block50_getSwEnd.fold.split7 %42]
  [label %block50_62_c3 ]
block50_getSwEnd:
  %43 = phi <Bits, 32bits> [%38, block50_62_c3], [%35, block40], [%36, block50_getSwEnd.fold.split], [%37, block50_getSwEnd.fold.split7]
  void call <Bits, 32bits> @hls.write(%43)
  i45 = call <Bits, 2bits, unsigned> @hls.read(i)
  %46 = EQ i45, <BitsVal 0>
  %47 = EQ i45, <BitsVal 2>
  %48 = TERNARY %46, %35, %36
  %49 = BitsAsSigned i45
  %50 = GT %49, <BitsVal -1>
  %51 = TERNARY %47, %37, %38
  %52 = TERNARY %50, %48, %51
  %53 = ADD %52, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd %46]
  [label %block50_getSwEnd_getSwEnd5 ]
block50_getSwEnd_getSwEnd_106_setSwEnd:
  %54 = phi <Bits, 32bits> [%53, block50_getSwEnd], [%35, block50_getSwEnd_getSwEnd5], [%35, block50_getSwEnd_getSwEnd6]
  %55 = phi <Bits, 32bits> [%36, block50_getSwEnd], [%53, block50_getSwEnd_getSwEnd5], [%36, block50_getSwEnd_getSwEnd6]
  %56 = phi <Bits, 32bits> [%37, block50_getSwEnd], [%37, block50_getSwEnd_getSwEnd5], [%60, block50_getSwEnd_getSwEnd6]
  %57 = phi <Bits, 32bits> [%38, block50_getSwEnd], [%38, block50_getSwEnd_getSwEnd5], [%59, block50_getSwEnd_getSwEnd6]
  br [label %block40 ]
block50_getSwEnd_getSwEnd5:
  %58 = EQ i45, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd %58]
  [label %block50_getSwEnd_getSwEnd6 ]
block50_getSwEnd_getSwEnd6:
  %59 = TERNARY %47, %38, %53
  %60 = TERNARY %47, %53, %37
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd.fold.split:
  br [label %block50_getSwEnd ]
block50_getSwEnd.fold.split7:
  br [label %block50_getSwEnd ]
block50_62_c3:
  br [label %block50_getSwEnd ]
}