from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ioProxyStream import IoProxyStream
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamLoopUnroll, \
    PyBytecodeLoopFlattenUsingIf
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel, PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from tests.io.amba.axi4Stream._baseAxi4SPktInPktOutTC import BaseAxi4SPktInPktOutTC


class Axi4SCopyWithLookahead(HwModule):
    """
    Optionally read second byte from input stream
    """
    AXI_CLS = Axi4Stream

    @override
    def hwConfig(self) -> None:
        self.AXI_CLS.hwConfig(self)
        self.COPY_WORD_WIDTH = HwParam(32)
        self.ALIGN_LOOP_BODY_BEGIN_BY_PREQUEL_EXTRACT = HwParam(True)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = self.AXI_CLS()
            self.tx = self.AXI_CLS()._m()

    # @hlsBytecode
    # def _forwardPacket(self, rx: IoProxyStream, commonHeader: AnyHBitsValue, tx: IoProxyStream):
    #    tx.writeStartOfFrame()
    #    word = commonHeader.data
    #    loopWordTy = word._dtype
    #    # sof = commonHeader._isSoF()
    #    eof = commonHeader._isEoF()
    #    while b1:
    #        PyBytecodeBlockLabel("_forwardPacket.copyLoop")
    #        tx.write(word, eof=eof)  # sof=sof,
    #        if eof:
    #            break
    #        w = rx.read(loopWordTy)
    #        word = w.data
    #        # sof = w._isSoF()
    #        eof = w._isEoF()
    #        PyBytecodeStreamLoopUnroll(tx.interface, alignLoopBodyBeginByPrequelExtract=self.ALIGN_LOOP_BODY_BEGIN_BY_PREQUEL_EXTRACT)
    #
    #    tx.writeEndOfFrame()

    @hlsBytecode
    def _forwardPacket(self, rx: IoProxyStream, commonHeader: AnyHBitsValue, tx: IoProxyStream):
        tx.writeStartOfFrame()
        word = commonHeader.data
        loopWordTy = word._dtype
        # sof = commonHeader._isSoF()
        eof = commonHeader._isEoF()
        tx.write(word, mask=commonHeader.strb if self.USE_STRB else None, eof=eof)  # sof=sof,
        while ~eof:
            # :note: No matteher the width of the read chunk size and the data width of interface
            # this loop should end up processing 1 word/clk
            PyBytecodeBlockLabel("copyLoop")
            w = rx.read(loopWordTy, reliable=False)
            word = w.data
            # sof = w._isSoF()
            eof = w._isEoF()
            tx.write(word, mask=w.strb if self.USE_STRB else None, eof=eof)  # sof=sof,
            # :note: unroll for tx because it is expected to be the bottleneck
            PyBytecodeStreamLoopUnroll(
                tx.interface,
                # :note: align of the loop greatly simplifies the state space of the loop loop, reducing compilation time
                alignLoopBodyBeginByPrequelExtract=self.ALIGN_LOOP_BODY_BEGIN_BY_PREQUEL_EXTRACT,
                # :note: fused with child loop entry in ext iteration of word loop so we can merge
                # presequel into the child loop
                followup_unrolled=PyBytecodeLoopFlattenUsingIf(PyBytecodeLoopFlattenUsingIf.Mode.CHILD_LOOP_ENTRY_IN_NEXT_ITERATION)
            )

        tx.writeEndOfFrame()
        PyBytecodeBlockLabel("_forwardPacket.ret")

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream,):
        while b1:
            PyBytecodeBlockLabel("mainLoop")
            rx.readStartOfFrame()
            commonHeader = rx.read(HBits(self.COPY_WORD_WIDTH), reliable=False)
            PyBytecodeInline(self._forwardPacket)(rx, commonHeader, tx)
            rx.readEndOfFrame()
            PyBytecodeBlockLabel("mainLoop.latch")

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        rx = IoProxyAxi4Stream(hls, self.rx)
        tx = IoProxyAxi4Stream(hls, self.tx)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, rx, tx))
        hls.compile()


class Axi4SCopyWithLookaheadTC(BaseAxi4SPktInPktOutTC):

    def _test(self, DATA_WIDTH:int, COPY_WORD_WIDTH:int, FRAME_LENGTHS=[1, 2, 3], freq=int(1e6), rtlSimTimeMultiplier=1.1, USE_STRB=True):
        dut = Axi4SCopyWithLookahead()
        dut.USE_STRB = USE_STRB
        dut.CLK_FREQ = freq
        dut.DATA_WIDTH = DATA_WIDTH
        dut.COPY_WORD_WIDTH = COPY_WORD_WIDTH

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        BaseAxi4SPktInPktOutTC._test(self, dut, refFrames, refFrames, freq=freq,
                                     rtlSimTimeMultiplier=rtlSimTimeMultiplier)

    #    self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
    #
    #    fu = Axi4StreamSimFrameUtils.from_HwIO(dut.dataIn)
    #    refFrames = []
    #    for LEN in LENS:
    #        data_B = list(range(LEN))
    #        refFrames.append(data_B)
    #        fu.send_bytes(data_B, dut.dataIn._ag.data)
    #
    #    t = int(freq_to_period(dut.clk.FREQ)) * (len(dut.dataIn._ag.data) + 10)
    #    self.runSim(t)
    #    for refF in refFrames:
    #        off, f = fu.receive_bytes(dut.dataOut._ag.data)
    #        self.assertEqual(off, 0)
    #        self.assertSequenceEqual(f, refF)
    #    self.assertTrue(not dut.dataOut._ag.data)

    def test_8dw_8(self):
        self._test(8, 8, FRAME_LENGTHS=[1, 2, 3], USE_STRB=False)

    def test_16dw_8(self):
        self._test(16, 8, FRAME_LENGTHS=[2, 4, 6], USE_STRB=False)

    def test_16dw_8_strb(self):
        self._test(16, 8, FRAME_LENGTHS=[2, 4, 6], USE_STRB=True)

    def test_32dw_8(self):
        self._test(32, 8, FRAME_LENGTHS=[4, 8, 12], USE_STRB=False)

    def test_32dw_16(self):
        self._test(32, 16, FRAME_LENGTHS=[2, 4, 6])

    def test_64dw_32(self):
        self._test(64, 32, FRAME_LENGTHS=[4, 8, 12])

    #def test_1024dw_32(self):
    #    # this should ~2s on 3GHz cpu
    #    self._test(1024, 8)

    def test_384dw_32(self):
        self._test(384, 8)

    def test_384dw_32_strb(self):
        self._test(384, 8, FRAME_LENGTHS=[4, 8, 12], USE_STRB=True)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.virtual import VirtualHlsPlatform

    m = Axi4SCopyWithLookahead()
    m.USE_STRB = False
    m.DATA_WIDTH = 64
    m.COPY_WORD_WIDTH = 16
    m.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                           llvmCliArgs=[
                               # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                               # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                               # LLVM_CLI_COMMON_OPTS.PRINT_MODULE_SCOPE,
                               # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                               ]
                           )
    # print(to_rtl_str(m, target_platform=p))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SCopyWithLookaheadTC)
    # suite = unittest.TestSuite([Axi4SCopyWithLookaheadTC("test_16dw_8")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
