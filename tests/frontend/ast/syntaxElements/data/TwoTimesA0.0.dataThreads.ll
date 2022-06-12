########### Thread 0 ###########
blocks:
    t0_TwoTimesA_TC_test0__TwoTimesA0_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 4 <Signal a <Bits, 8bits>>>
    <HlsNetNodeOperator 5 INDEX [4:0, 6:0]>
    <HlsNetNodeConst 6 <HSliceVal slice(<BitsVal 7>, <BitsVal 0>, <BitsVal -1>)>>
    <HlsNetNodeConst 7 <BitsVal 0>>
    <HlsNetNodeOperator 8 CONCAT [5:0, 7:0]>
    <HlsNetNodeWrite 9 <Signal b <Bits, 8bits>> <- <HlsNetNodeOut <HlsNetNodeOperator 8 CONCAT> [0]>>

