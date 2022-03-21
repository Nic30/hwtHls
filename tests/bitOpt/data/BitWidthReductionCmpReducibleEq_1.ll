define dso_local i32 @main() #0 {
entry:
  br [label %mainThread ]
mainThread:
  br [label %block12 ]
block12:
  a0 = call <Bits, 8bits, unsigned> @hls.read(a)
  b1 = call <Bits, 8bits, unsigned> @hls.read(b)
  %3 = EQ a0, b1
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  %6 = CONCAT <BitsVal 0>, a0
  %7 = CONCAT <BitsVal 0>, b1
  %8 = EQ %6, %7
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %10 = CONCAT <BitsVal 1>, a0
  %11 = CONCAT <BitsVal 1>, b1
  %12 = EQ %10, %11
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %14 = CONCAT <BitsVal 0>, a0
  %15 = CONCAT <BitsVal 1>, b1
  %16 = EQ %14, %15
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %18 = CONCAT <BitsVal 0>, a0
  %19 = CONCAT <BitsVal 255>, b1
  %20 = EQ %18, %19
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %22 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %23 = CONCAT %22, <BitsVal 0>
  %24 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %25 = CONCAT %23, %24
  %26 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %27 = CONCAT %26, <BitsVal 0>
  %28 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %29 = CONCAT %27, %28
  %30 = EQ %25, %29
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %32 = INDEX a0, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %33 = CONCAT %32, <BitsVal 0>
  %34 = INDEX a0, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %35 = CONCAT %33, %34
  %36 = INDEX b1, <HSliceVal slice(<BitsVal 8>, <BitsVal 4>, <BitsVal -1>)>
  %37 = CONCAT %36, <BitsVal 255>
  %38 = INDEX b1, <HSliceVal slice(<BitsVal 4>, <BitsVal 0>, <BitsVal -1>)>
  %39 = CONCAT %37, %38
  %40 = EQ %35, %39
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  br [label %mainThread ]
}