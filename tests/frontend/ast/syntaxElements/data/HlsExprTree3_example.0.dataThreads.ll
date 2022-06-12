########### Thread 0 ###########
blocks:
    t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 4 <Signal a <Bits, 32bits, unsigned>>>
    <HlsNetNodeRead 5 <Signal b <Bits, 32bits, unsigned>>>
    <HlsNetNodeRead 6 <Signal c <Bits, 32bits, unsigned>>>
    <HlsNetNodeRead 7 <Signal d <Bits, 32bits, unsigned>>>
    <HlsNetNodeOperator 8 ADD [5:0, 4:0]>
    <HlsNetNodeOperator 9 ADD [8:0, 6:0]>
    <HlsNetNodeOperator 10 MUL [9:0, 7:0]>
    <HlsNetNodeWrite 11 <Signal f1 <Bits, 32bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 10 MUL> [0]>>

########### Thread 1 ###########
blocks:
    t0_HlsExprTree3_example_TC_test_ll__HlsExprTree3_example_whC
nodes:
    <HlsNetNodeOutLazy 2>
    <HlsNetNodeRead 12 <Signal x <Bits, 32bits, unsigned>>>
    <HlsNetNodeRead 13 <Signal y <Bits, 32bits, unsigned>>>
    <HlsNetNodeOperator 14 ADD [13:0, 12:0]>
    <HlsNetNodeRead 15 <Signal z <Bits, 32bits, unsigned>>>
    <HlsNetNodeOperator 16 MUL [14:0, 15:0]>
    <HlsNetNodeWrite 17 <Signal f2 <Bits, 32bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 16 MUL> [0]>>
    <HlsNetNodeRead 18 <Signal w <Bits, 32bits, unsigned>>>
    <HlsNetNodeOperator 19 MUL [18:0, 14:0]>
    <HlsNetNodeWrite 20 <Signal f3 <Bits, 32bits, unsigned>> <- <HlsNetNodeOut <HlsNetNodeOperator 19 MUL> [0]>>

