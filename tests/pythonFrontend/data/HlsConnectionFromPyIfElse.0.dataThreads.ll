########### Thread 0 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeRead 2 <Signal i <Bits, 8bits, unsigned>>>
    <HlsNetNodeConst 3 <BitsVal 2>>
    <HlsNetNodeOperator 4 EQ [2:0, 3:0]>
    <HlsNetNodeConst 5 <BitsVal 1>>
    <HlsNetNodeOperator 6 XOR [4:0, 5:0]>
    <HlsNetNodeConst 7 <BitsVal 0>>
    <HlsNetNodeConst 8 <BitsVal 1>>
    <HlsNetNodeOperator 9 CONCAT [7:0, 6:0]>
    <HlsNetNodeOperator 10 CONCAT [9:0, 8:0]>
    <HlsNetNodeOperator 11 CONCAT [10:0, 4:0]>
    <HlsNetNodeWrite 12 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 11 CONCAT> [0]>>

