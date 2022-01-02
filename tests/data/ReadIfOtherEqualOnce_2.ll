define dso_local i32 @main() #0 {
top:
  a = call <Bits, 8bits> @hls.read(a)
  %1 = EQ a, <BitsVal 3>
  br [label %top_If %1]
  [label %top_IfE ]
top_If:
  b = call <Bits, 8bits> @hls.read(b)
  br [label %top_IfE ]
top_IfE:
}