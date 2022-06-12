########### Thread 0 ###########
blocks:
    t0_HlsSlicingTC_test_HlsSlice2TmpHlsVarSlice__HlsSlice2TmpHlsVarSlice_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 4 <Signal a <Bits, 16bits, unsigned>>>
    <HlsNetNodeConst 5 <BitsVal 0>>
    <HlsNetNodeConst 6 <BitsVal 1>>
    <HlsNetNodeConst 7 <BitsVal 0>>
    <HlsNetNodeOperator 8 CONCAT [5:0, 6:0]>
    <HlsNetNodeOperator 9 CONCAT [8:0, 7:0]>
    <HlsNetNodeOperator 10 CONCAT [9:0, 4:0]>
    <HlsNetNodeWrite 11 <Signal b <Bits, 32bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 10 CONCAT> [0]>>

