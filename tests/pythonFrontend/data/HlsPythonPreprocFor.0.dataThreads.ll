########### Thread 0 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeConst 2 <BitsVal 0>>
    <HlsNetNodeWrite 3 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 0> [0]>>

########### Thread 1 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeConst 4 <BitsVal 1>>
    <HlsNetNodeWrite 5 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 1> [0]>>

########### Thread 2 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeConst 6 <BitsVal 2>>
    <HlsNetNodeWrite 7 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 2> [0]>>

########### Thread 3 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeConst 8 <BitsVal 3>>
    <HlsNetNodeWrite 9 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 3> [0]>>

########### Thread 4 ###########
blocks:
    mainThread
nodes:
    <HlsNetNodeOutLazy 0>
    <HlsNetNodeConst 10 <BitsVal 4>>
    <HlsNetNodeWrite 11 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 4> [0]>>

