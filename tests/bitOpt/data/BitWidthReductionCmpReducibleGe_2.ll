define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  a41 = call <Bits, 8bits, unsigned> @hls.read(a)
  b42 = call <Bits, 8bits, unsigned> @hls.read(b)
  %43 = GE a41, b42
  void call <Bits, 1bit> @hls.write(%43)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  void call <Bits, 1bit> @hls.write(%43)
  %47 = CONCAT <BitsVal 1>, a41
  %48 = CONCAT <BitsVal 1>, b42
  %49 = GE %47, %48
  void call <Bits, 1bit> @hls.write(%49)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  %53 = INDEX a41, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %54 = INDEX a41, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %55 = CONCAT <BitsVal 0>, %54
  %56 = CONCAT %53, %55
  %57 = INDEX b42, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %58 = INDEX b42, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %59 = CONCAT <BitsVal 0>, %58
  %60 = CONCAT %57, %59
  %61 = GE %56, %60
  void call <Bits, 1bit> @hls.write(%61)
  %63 = INDEX a41, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %64 = INDEX a41, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %65 = CONCAT <BitsVal 0>, %64
  %66 = CONCAT %63, %65
  %67 = INDEX b42, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %68 = INDEX b42, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %69 = CONCAT <BitsVal 255>, %68
  %70 = CONCAT %67, %69
  %71 = GE %66, %70
  void call <Bits, 1bit> @hls.write(%71)
  br [label %mainThread ]
}