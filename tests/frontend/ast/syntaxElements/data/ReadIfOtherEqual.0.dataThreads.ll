########### Thread 0 ###########
blocks:
    t0_ReadIfTc_test_ReadIfOtherEqual_ll__ReadIfOtherEqual_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 4 <Handshaked a>>
    <HlsNetNodeConst 5 <BitsVal 3>>
    <HlsNetNodeOperator 6 NE [4:0, 5:0]>
    <HlsNetNodeRead 7 <Handshaked b>>
    <HlsNetNodeOperator 8 AND [<HlsNetNodeOutLazy 2>, 6:0]>

