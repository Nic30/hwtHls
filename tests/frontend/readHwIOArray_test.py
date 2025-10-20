#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOArray import HwIOArray
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from tests.frontend.trivial import WriteOnce
from hwt.simulator.simTestCase import SimTestCase
from hwtSimApi.utils import freq_to_period
from hwtHls.platform.virtual import VirtualHlsPlatform


class ReadHStructWithHwIOArray1d(WriteOnce):

    @override
    def hwDeclr(self):
        addClkRstn(self)

        i = self.dataIn = HwIOStructRdVld()
        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = i.T = HStruct(
            (HBits(self.DATA_WIDTH)[2], "arr0"),
        )

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            d = hls.read(self.dataIn).data
            hls.write(d, self.dataOut, mayBecomeFlushable=False)


class ReadHStructWithHwIOArray2d(ReadHStructWithHwIOArray1d):

    @override
    def hwDeclr(self):
        addClkRstn(self)

        i = self.dataIn = HwIOStructRdVld()
        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = i.T = HStruct(
            (HBits(self.DATA_WIDTH)[3][2], "arr0"),
        )


class ReadHwIOArray1d(ReadHStructWithHwIOArray1d):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        t = HBits(self.DATA_WIDTH)
        self.dataIn = HwIOArray(HwIOSignal(t) for _ in range(2))
        self.dataOut = HwIOArray(HwIOSignal(t) for _ in range(2))._m()

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        t = HBits(self.DATA_WIDTH)[2]
        while b1:
            d = hls.read(self.dataIn).data
            assert d._dtype == t, (d._dtype, t)
            hls.write(d, self.dataOut, mayBecomeFlushable=False)


class ReadHwIOArray_TC(SimTestCase):

    def _testRunSim(self, dut, data):
        dut.dataIn._ag.data.extend(data)
        self.runSim((len(data) + 1) * int(freq_to_period(dut.CLK_FREQ)))
        self.assertValSequenceEqual(dut.dataOut._ag.data, data)

    def test_ReadHStructWithHwIOArray1d(self):
        dut = ReadHStructWithHwIOArray1d()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        data = [(0, 1),
                (2, 3),
                (4, 5),
                ]
        # because HwIOStructRdVld has "data" prop.
        data = [(d,) for d in data]
        self._testRunSim(dut, data)

    def test_ReadHStructWithHwIOArray2d(self):
        dut = ReadHStructWithHwIOArray2d()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        data = [
            ((0, 1, 2),
              (3, 4, 5)),
            ((6, 7, 8),
             (9, 10, 11)),
        ]
        # because HwIOStructRdVld has "data" prop.
        data = [(d,) for d in data]
        self._testRunSim(dut, data)

    def test_ReadHwIOArray1d(self):
        dut = ReadHwIOArray1d()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        data = [(0, 1),
                (2, 3),
                (4, 5),
                ]
        dut.dataIn._ag.extendDataFromTuples(data)
        self.runSim((len(data) + 1) * int(freq_to_period(dut.CLK_FREQ)))
        self.assertValSequenceEqual(list(dut.dataOut._ag.getDataAsTuples()), data)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = ReadHStructWithHwIOArray2d()
    m.CLK_FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(ReadHwIOArray_TC)
    # suite = unittest.TestSuite([ReadHwIOArray_TC('test_HlsSlice2TmpHlsVarSlice')])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

