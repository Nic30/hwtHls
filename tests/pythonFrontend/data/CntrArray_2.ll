define dso_local i32 @main() #0 {
mainThread:
  br [label %block40 ]
block40:
  %39 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%58, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %40 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%59, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %41 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%60, block50_getSwEnd_getSwEnd_106_setSwEnd]
  %42 = phi <Bits, 32bits> [<BitsVal 0>, mainThread], [%61, block50_getSwEnd_getSwEnd_106_setSwEnd]
  o_addr43 = call <Bits, 2bits, unsigned> @hls.read(o_addr)
  %44 = EQ o_addr43, <BitsVal 0>
  %45 = EQ o_addr43, <BitsVal 1>
  %46 = EQ o_addr43, <BitsVal 2>
  br [label %block50_getSwEnd %44]
  [label %block50_getSwEnd.fold.split %45]
  [label %block50_getSwEnd.fold.split7 %46]
  [label %block50_62_c3 ]
block50_getSwEnd:
  %47 = phi <Bits, 32bits> [%42, block50_62_c3], [%39, block40], [%40, block50_getSwEnd.fold.split], [%41, block50_getSwEnd.fold.split7]
  void call <Bits, 32bits> @hls.write(%47)
  i49 = call <Bits, 2bits, unsigned> @hls.read(i)
  %50 = EQ i49, <BitsVal 0>
  %51 = EQ i49, <BitsVal 2>
  %52 = TERNARY %50, %39, %40
  %53 = BitsAsSigned i49
  %54 = GT %53, <BitsVal -1>
  %55 = TERNARY %51, %41, %42
  %56 = TERNARY %54, %52, %55
  %57 = ADD %56, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd %50]
  [label %block50_getSwEnd_getSwEnd5 ]
block50_getSwEnd_getSwEnd_106_setSwEnd:
  %58 = phi <Bits, 32bits> [%57, block50_getSwEnd], [%39, block50_getSwEnd_getSwEnd5], [%39, block50_getSwEnd_getSwEnd6]
  %59 = phi <Bits, 32bits> [%40, block50_getSwEnd], [%57, block50_getSwEnd_getSwEnd5], [%40, block50_getSwEnd_getSwEnd6]
  %60 = phi <Bits, 32bits> [%41, block50_getSwEnd], [%41, block50_getSwEnd_getSwEnd5], [%64, block50_getSwEnd_getSwEnd6]
  %61 = phi <Bits, 32bits> [%42, block50_getSwEnd], [%42, block50_getSwEnd_getSwEnd5], [%63, block50_getSwEnd_getSwEnd6]
  br [label %block40 ]
block50_getSwEnd_getSwEnd5:
  %62 = EQ i49, <BitsVal 1>
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd %62]
  [label %block50_getSwEnd_getSwEnd6 ]
block50_getSwEnd_getSwEnd6:
  %63 = TERNARY %51, %42, %57
  %64 = TERNARY %51, %57, %41
  br [label %block50_getSwEnd_getSwEnd_106_setSwEnd ]
block50_getSwEnd.fold.split:
  br [label %block50_getSwEnd ]
block50_getSwEnd.fold.split7:
  br [label %block50_getSwEnd ]
block50_62_c3:
  br [label %block50_getSwEnd ]
}