define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL10i0_10 ]
blockL10i0_10:
  a0 = call <Bits, 8bits, unsigned> @hls.read(a)
  b1 = call <Bits, 8bits, unsigned> @hls.read(b)
  %3 = LE a0, b1
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  void call <Bits, 1bit> @hls.write(<BitsVal 1>)
  %6 = CONCAT a0, <BitsVal 0>
  %7 = CONCAT b1, <BitsVal 0>
  %8 = LE %6, %7
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %10 = CONCAT a0, <BitsVal 1>
  %11 = CONCAT b1, <BitsVal 1>
  %12 = LE %10, %11
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %14 = CONCAT a0, <BitsVal 0>
  %15 = CONCAT b1, <BitsVal 1>
  %16 = LE %14, %15
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %18 = CONCAT a0, <BitsVal 0>
  %19 = CONCAT b1, <BitsVal 255>
  %20 = LE %18, %19
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %22 = INDEX a0, <HSliceVal slice(8, 4, -1)>
  %23 = CONCAT <BitsVal 0>, %22
  %24 = INDEX a0, <HSliceVal slice(4, 0, -1)>
  %25 = CONCAT %24, %23
  %26 = INDEX b1, <HSliceVal slice(8, 4, -1)>
  %27 = CONCAT <BitsVal 0>, %26
  %28 = INDEX b1, <HSliceVal slice(4, 0, -1)>
  %29 = CONCAT %28, %27
  %30 = LE %25, %29
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  %32 = INDEX a0, <HSliceVal slice(8, 4, -1)>
  %33 = CONCAT <BitsVal 0>, %32
  %34 = INDEX a0, <HSliceVal slice(4, 0, -1)>
  %35 = CONCAT %34, %33
  %36 = INDEX b1, <HSliceVal slice(8, 4, -1)>
  %37 = CONCAT <BitsVal 255>, %36
  %38 = INDEX b1, <HSliceVal slice(4, 0, -1)>
  %39 = CONCAT %38, %37
  %40 = LE %35, %39
  void call <Bits, "bool", 1bit> @hls.write(sig_)
  br [label %blockL10i0_10 ]
}