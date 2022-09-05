define dso_local i32 @main() #0 {
mainThread:
  br [label %block0 ]
block0:
  br [label %blockL10i0_10 ]
blockL10i0_10:
  a0 = call <Bits, 8bits, unsigned> @hls.read(a)
  b1 = call <Bits, 8bits, unsigned> @hls.read(b)
  %3 = GT a0, b1
  void call <Bits, "bool", 1bit> @hls.write(a > b)
  void call <Bits, 1bit> @hls.write(<BitsVal 0>)
  %6 = CONCAT a0, <BitsVal 0>
  %7 = CONCAT b1, <BitsVal 0>
  %8 = GT %6, %7
  void call <Bits, "bool", 1bit> @hls.write(Concat(Bits(8).from_py(0), a._reinterpret_cast(Bits(8))) > Concat(Bits(8).from_py(0), b._reinterpret_cast(Bits(8))))
  %10 = CONCAT a0, <BitsVal 1>
  %11 = CONCAT b1, <BitsVal 1>
  %12 = GT %10, %11
  void call <Bits, "bool", 1bit> @hls.write(Concat(Bits(8).from_py(1), a._reinterpret_cast(Bits(8))) > Concat(Bits(8).from_py(1), b._reinterpret_cast(Bits(8))))
  %14 = CONCAT a0, <BitsVal 0>
  %15 = CONCAT b1, <BitsVal 1>
  %16 = GT %14, %15
  void call <Bits, "bool", 1bit> @hls.write(Concat(Bits(8).from_py(0), a._reinterpret_cast(Bits(8))) > Concat(Bits(8).from_py(1), b._reinterpret_cast(Bits(8))))
  %18 = CONCAT a0, <BitsVal 0>
  %19 = CONCAT b1, <BitsVal 255>
  %20 = GT %18, %19
  void call <Bits, "bool", 1bit> @hls.write(Concat(Bits(8).from_py(0), a._reinterpret_cast(Bits(8))) > Concat(Bits(8).from_py(255), b._reinterpret_cast(Bits(8))))
  %22 = INDEX a0, <HSliceVal slice(8, 4, -1)>
  %23 = CONCAT <BitsVal 0>, %22
  %24 = INDEX a0, <HSliceVal slice(4, 0, -1)>
  %25 = CONCAT %24, %23
  %26 = INDEX b1, <HSliceVal slice(8, 4, -1)>
  %27 = CONCAT <BitsVal 0>, %26
  %28 = INDEX b1, <HSliceVal slice(4, 0, -1)>
  %29 = CONCAT %28, %27
  %30 = GT %25, %29
  void call <Bits, "bool", 1bit> @hls.write(Concat(Concat(a[8:4]._reinterpret_cast(Bits(4)), Bits(8).from_py(0)), a[4:0]._reinterpret_cast(Bits(4))) > Concat(Concat(b[8:4]._reinterpret_cast(Bits(4)), Bits(8).from_py(0)), b[4:0]._reinterpret_cast(Bits(4))))
  %32 = INDEX a0, <HSliceVal slice(8, 4, -1)>
  %33 = CONCAT <BitsVal 0>, %32
  %34 = INDEX a0, <HSliceVal slice(4, 0, -1)>
  %35 = CONCAT %34, %33
  %36 = INDEX b1, <HSliceVal slice(8, 4, -1)>
  %37 = CONCAT <BitsVal 255>, %36
  %38 = INDEX b1, <HSliceVal slice(4, 0, -1)>
  %39 = CONCAT %38, %37
  %40 = GT %35, %39
  void call <Bits, "bool", 1bit> @hls.write(Concat(Concat(a[8:4]._reinterpret_cast(Bits(4)), Bits(8).from_py(0)), a[4:0]._reinterpret_cast(Bits(4))) > Concat(Concat(b[8:4]._reinterpret_cast(Bits(4)), Bits(8).from_py(255)), b[4:0]._reinterpret_cast(Bits(4))))
  br [label %blockL10i0_10 ]
}