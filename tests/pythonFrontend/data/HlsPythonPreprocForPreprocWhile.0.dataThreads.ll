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
    <HlsNetNodeConst 6 <BitsVal 1>>
    <HlsNetNodeWrite 7 <Signal o <Bits, 8bits, unsigned>> <- <HlsNetNodeOut <BitsVal 1> [0]>>

