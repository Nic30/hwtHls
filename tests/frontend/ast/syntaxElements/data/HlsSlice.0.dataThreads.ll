########### Thread 0 ###########
blocks:
    t0_HlsSlicingTC_test_slice__HlsSlice_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 4 <Signal a <Bits, 32bits, unsigned>>>
    <HlsNetNodeOperator 5 INDEX [4:0, 6:0]>
    <HlsNetNodeConst 6 <HSliceVal slice(<BitsVal 16>, <BitsVal 0>, <BitsVal -1>)>>
    <HlsNetNodeWrite 7 <Signal b <Bits, 16bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 5 INDEX> [0]>>

