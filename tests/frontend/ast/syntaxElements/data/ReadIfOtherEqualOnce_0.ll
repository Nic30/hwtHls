define dso_local i32 @main() #0 {
top:
  br [label %top_IfC ]
top_IfC:
  a0 = call <Bits, 8bits> @hls.read(a)
  %2 = EQ a0, <BitsVal 3>
  br [label %top_If %2]
  [label %top_IfE ]
top_If:
  b1 = call <Bits, 8bits> @hls.read(b)
  br [label %top_IfE ]
top_IfE:
}