########### Thread 0 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeRead 2 <Signal i <Bits, 8bits, unsigned>>>
    <HlsNetNodeConst 3 <BitsVal 10>>
    <HlsNetNodeOperator 4 EQ [2:0, 3:0]>
    <HlsNetNodeConst 5 <BitsVal 2>>
    <HlsNetNodeOperator 6 EQ [2:0, 5:0]>
    <HlsNetNodeConst 7 <BitsVal 1>>
    <HlsNetNodeOperator 8 CONCAT [7:0, 4:0]>
    <HlsNetNodeConst 9 <BitsVal 1>>
    <HlsNetNodeMux 10 [9:0, 6:0, 8:0]>
    <HlsNetNodeOperator 11 INDEX [10:0, 12:0]>
    <HlsNetNodeConst 12 <HSliceVal slice(<BitsVal 1>, <BitsVal 0>, <BitsVal -1>)>>
    <HlsNetNodeConst 13 <BitsVal 0>>
    <HlsNetNodeConst 14 <BitsVal 1>>
    <HlsNetNodeOperator 15 CONCAT [13:0, 11:0]>
    <HlsNetNodeOperator 16 CONCAT [15:0, 14:0]>
    <HlsNetNodeOperator 17 CONCAT [16:0, 11:0]>
    <HlsNetNodeWrite 18 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 17 CONCAT> [0]>>

