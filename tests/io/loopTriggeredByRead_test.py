from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLoopFlattenUsingIf
from hwtHls.frontend.pyBytecode.pragmaInstruction import PyBytecodeIntrinsicAssume, PyBytecodeNoSplitSlices
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from tests.frontend.pyBytecode.stmWhile import TRUE
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from pyMathBitPrecise.bit_utils import mask


class ShiftSequential1Loop(HwModule):

    @override
    def hwConfig(self) -> None:
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    @override
    def hwDeclr(self) -> None:
        with self._hwParamsShared():
            addClkRstn(self)
            dataIn = HwIOStructRdVld()
            dataIn.T = HStruct(
                (HBits(self.DATA_WIDTH), "data"),
                (HBits(log2ceil(self.DATA_WIDTH + 1)), "sh"),
            )
            self.i = dataIn
            self.o = HwIODataRdVld()._m()

    def model(self, dataIn, dataOut):
        for dIn in dataIn:
            d, sh = dIn
            res = d._dtype.from_py(int(d) >> int(sh))
            dataOut.append(res)

    @hlsBytecode
    def mainThread(self, hls: HlsScope, dataIn: HwIOStructRdVld, dataOut: HwIOStructRdVld):
        d = dataIn.T.from_py({'sh':0})
        while TRUE:
            if d.sh._eq(0):
                d = hls.read(dataIn).data
                PyBytecodeIntrinsicAssume()(d.sh > 0)
            # disable costly bitblasting because there is nothing to optimize
            PyBytecodeNoSplitSlices(d.data)
            d.data >>= 1
            d.sh -= 1
            if d.sh._eq(0):
                hls.write(d.data, dataOut)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, self.i, self.o))
        hls.compile()


class ShiftSequential2Loops(ShiftSequential1Loop):

    @hlsBytecode
    def mainThread(self, hls: HlsScope, dataIn: HwIOStructRdVld, dataOut: HwIOStructRdVld):
        while TRUE:
            d = hls.read(dataIn).data
            # disable check in first iteration to simplify circuit
            # :note: however this adds false liveness to d.sh in last iteration
            #        this livenes should be removed by PruneLoopPhiDeadIncomingValuesPass
            PyBytecodeIntrinsicAssume()(d.sh > 0)

            # PyBytecodeNoSplitSlices(d.data)
            while d.sh != 0:
                # disable costly bitblasting because there is nothing to optimize
                PyBytecodeNoSplitSlices(d.data)
                d.data >>= 1
                d.sh -= 1
                # PyBytecodeNoSplitSlices(d.data)
                # merge this with parent loop to have just 1 loop with conditional input read
                PyBytecodeLoopFlattenUsingIf()

            hls.write(d.data, dataOut)


class ShiftSequential_TC(BaseIrMirRtl_TC):

    def test_ShiftSequential1Loop(self, dutCls=ShiftSequential1Loop):
        dut = dutCls()
        DW = dut.DATA_WIDTH
        OUT_CNT = DW * 3
        dTy = HBits(DW)
        SH_W = log2ceil(DW + 1)
        shTy = HBits(SH_W)
        m = dTy.from_py(mask(DW))
        dataIn = [
            (m, shTy.from_py(self._rand.randint(1, DW)))
            for _ in range(OUT_CNT)
        ]

        def prepareIrAndMirArgs():
            dataOut = []
            return ((d[1]._concat(d[0]) for d in dataIn), dataOut)

        self._test_OneInOneOut(dut, dut.model, dataIn,
                   OUT_CNT * 200, OUT_CNT * 200,
                   OUT_CNT * 200, (OUT_CNT * 8) + 2,
                   prepareIrAndMirArgs=prepareIrAndMirArgs)

    def test_ShiftSequential2Loops(self):
        self.test_ShiftSequential1Loop(dutCls=ShiftSequential2Loops)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    
    m = ShiftSequential1Loop()
    m.FREQ = int(50e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ShiftSequential_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(ShiftSequential_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

