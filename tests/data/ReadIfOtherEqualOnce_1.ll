define dso_local i32 @main() #0 {
top:
  br [label %top_IfC ]
top_IfC:
  a = call <Bits, 8bits> @hls.read(a)
  %0 = EQ a, <BitsVal 3>
  br [label %top_If %0]
  [label %top_IfE ]
top_If:
  b = call <Bits, 8bits> @hls.read(b)
  br [label %top_IfE ]
top_IfE:
}