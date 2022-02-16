define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  a0 = call <Bits, 8bits, unsigned> @hls.read(a)
  b1 = call <Bits, 8bits, unsigned> @hls.read(b)
  %10 = NE a0, b1
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  %11 = CONCAT <BitsVal 0>, a0
  %12 = CONCAT <BitsVal 0>, b1
  %13 = NE %11, %12
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %14 = CONCAT <BitsVal 1>, a0
  %15 = CONCAT <BitsVal 1>, b1
  %16 = NE %14, %15
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %17 = CONCAT <BitsVal 0>, a0
  %18 = CONCAT <BitsVal 1>, b1
  %19 = NE %17, %18
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %20 = CONCAT <BitsVal 0>, a0
  %21 = CONCAT <BitsVal 255>, b1
  %22 = NE %20, %21
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %23 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %24 = CONCAT %23, <BitsVal 0>
  %25 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %26 = CONCAT %24, %25
  %27 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %28 = CONCAT %27, <BitsVal 0>
  %29 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %30 = CONCAT %28, %29
  %31 = NE %26, %30
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %32 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %33 = CONCAT %32, <BitsVal 0>
  %34 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %35 = CONCAT %33, %34
  %36 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %37 = CONCAT %36, <BitsVal 255>
  %38 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %39 = CONCAT %37, %38
  %40 = NE %35, %39
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  br [label %block0 ]
}