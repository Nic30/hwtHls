define dso_local i32 @main() #0 {
entry:
  br [label %block0 ]
block0:
  a0 = call <Bits, 8bits, unsigned> @hls.read(a)
  b1 = call <Bits, 8bits, unsigned> @hls.read(b)
  %9 = GE a0, b1
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %10 = CONCAT <BitsVal 0>, a0
  %11 = CONCAT <BitsVal 0>, b1
  %12 = GE %10, %11
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %13 = CONCAT <BitsVal 1>, a0
  %14 = CONCAT <BitsVal 1>, b1
  %15 = GE %13, %14
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %16 = CONCAT <BitsVal 0>, a0
  %17 = CONCAT <BitsVal 1>, b1
  %18 = GE %16, %17
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %19 = CONCAT <BitsVal 0>, a0
  %20 = CONCAT <BitsVal 255>, b1
  %21 = GE %19, %20
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %22 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %23 = CONCAT %22, <BitsVal 0>
  %24 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %25 = CONCAT %23, %24
  %26 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %27 = CONCAT %26, <BitsVal 0>
  %28 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %29 = CONCAT %27, %28
  %30 = GE %25, %29
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %31 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %32 = CONCAT %31, <BitsVal 0>
  %33 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %34 = CONCAT %32, %33
  %35 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %36 = CONCAT %35, <BitsVal 255>
  %37 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %38 = CONCAT %36, %37
  %39 = GE %34, %38
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  br [label %block0 ]
}