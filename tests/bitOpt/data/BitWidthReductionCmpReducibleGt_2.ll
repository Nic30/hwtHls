define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  a40 = call <Bits, 8bits, unsigned> @hls.read(a)
  b41 = call <Bits, 8bits, unsigned> @hls.read(b)
  %42 = GT a40, b41
  void call <Bits, 1bit> @hls.write(%42)
  void call <Bits, 1bit> @hls.write(%42)
  %45 = CONCAT <BitsVal 1>, a40
  %46 = CONCAT <BitsVal 1>, b41
  %47 = GT %45, %46
  void call <Bits, 1bit> @hls.write(%47)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  %51 = INDEX a40, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %52 = INDEX a40, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %53 = CONCAT <BitsVal 0>, %52
  %54 = CONCAT %51, %53
  %55 = INDEX b41, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %56 = INDEX b41, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %57 = CONCAT <BitsVal 0>, %56
  %58 = CONCAT %55, %57
  %59 = GT %54, %58
  void call <Bits, 1bit> @hls.write(%59)
  %61 = INDEX a40, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %62 = INDEX a40, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %63 = CONCAT <BitsVal 0>, %62
  %64 = CONCAT %61, %63
  %65 = INDEX b41, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %66 = INDEX b41, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %67 = CONCAT <BitsVal 255>, %66
  %68 = CONCAT %65, %67
  %69 = GT %64, %68
  void call <Bits, 1bit> @hls.write(%69)
  br [label %block0 ]
}