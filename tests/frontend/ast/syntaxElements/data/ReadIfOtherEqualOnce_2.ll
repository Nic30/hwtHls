define dso_local i32 @main() #0 {
top:
  a3 = call <Bits, 8bits> @hls.read(a)
  %4 = EQ a3, <BitsVal 3>
  br [label %top_If %4]
  [label %top_IfE ]
top_If:
  b5 = call <Bits, 8bits> @hls.read(b)
  br [label %top_IfE ]
top_IfE:
}