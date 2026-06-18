#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import struct

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.math.componentGenerators._genericHwModules import _FpAlu2HwModule
from tests.math.fp.fpcmp import IEEE754FpCmp, IEEE754FpCmpResult
from tests.math.fp.fptypes import IEEE754Fp32, IEEE754FpHConst
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class _TestIEEE754FpComparator(HwModule):

    @override
    def hwConfig(self) -> None:
        _BaseALU1HwModule.hwConfig(self)
        self.CLK_FREQ = int(20e6)
        self.T = IEEE754Fp32

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)

        t = self.T
        inT = HStruct(
            (t, "a"),
            (t, "b"),
        )
        _FpAlu2HwModule._addDataInDataOut(self, inT, HBits(2))

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            dIn = hls.read(self.data_in).data
            res = PyBytecodeInline(IEEE754FpCmp)(dIn.a, dIn.b)
            hls.write(res, self.data_out)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class IEEE754FpCmp_TC(SimTestCase):
    INPUT_DATA: list[tuple[float, float]] = [
        (6.239999771118164 , 3.140000104904175),  # GT  (0x40c7ae14, 0x4048f5c3),
        (-12.300000190734863 , -13.399999618530273),  # GT  (0xc144cccd, 0xc1566666),
        (15.300000190734863 , 2.299999952316284),  # GT  (0x4174cccd, 0x40133333),
        (12.300000190734863 , 14.300000190734863),  # LT  (0x4144cccd, 0x4164cccd),
        (-3.4000000953674316, -16.5),  # GT  (0xc059999a, 0xc1840000),
        (-1.2999999523162842, 2.299999952316284),  # LT  (0xbfa66666, 0x40133333),
        (13.300000190734863 , -14.300000190734863),  # GT  (0x4154cccd, 0xc164cccd),
        (6.239999771118164 , 6.239999771118164),  # EQ  (0x40c7ae14, 0x40c7ae14),
        (15.300000190734863 , 15.300000190734863),  # EQ  (0x4174cccd, 0x4174cccd),
    ]

    @staticmethod
    def model(a: float, b: float) -> int:
        if a == b:
            return IEEE754FpCmpResult.EQ
        elif a < b:
            return IEEE754FpCmpResult.LT
        elif a > b:
            return IEEE754FpCmpResult.GT
        else:
            return IEEE754FpCmpResult.UNKNOWN

    def test_cmp_py(self):
        T = IEEE754Fp32
        for (_a, _b) in self.INPUT_DATA:
            a = T.from_py(_a)
            b = T.from_py(_b)
            res = IEEE754FpCmp(a, b)
            # check if conversion from py int to hvalue and to float is correct
            resRef = self.model(_a, _b)
            self.assertValEqual(res, int(resRef),
                                msg=(_a, IEEE754FpCmpResult.toStr(res), _b,
                                     'expected', IEEE754FpCmpResult.toStr(resRef)))

    def test_cmp(self):
        dut = _TestIEEE754FpComparator()
        dut.T = IEEE754Fp32
        dataInIr: list[HBitsConst] = []
        dataInRtl: list[tuple[tuple[HBitsConst, HBitsConst, HBitsConst], ...]] = []
        resRef: list[HBitsConst] = []
        T = dut.T
        t = HBits(dut.T.bit_length() * 2)
        for (_a, _b) in self.INPUT_DATA:
            a = T.from_py(_a)
            b = T.from_py(_b)
            dataInIr.append(t.from_py(struct.pack("ff", _a, _b)))
            dataInRtl.append(tuple((v.mantissa._vec(), v.exponent._vec(), v.sign)
                                   for v in (a, b)))
            _resRef = int(self.model(_a, _b))
            resRef.append(_resRef)

        platform = VirtualHlsPlatform()
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.bindDataByInOut((dataInIr,), (resRef,), PORT_NAMES=('data_in', 'data_out'))
        passTests.install(platform)
        self.compileSimAndStart(dut, target_platform=platform)

        dut.data_in._ag.data.extend(dataInRtl)
        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        self.runSim((len(self.INPUT_DATA) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.data_out._ag.data, resRef,
                                    [(a, b)
                                     for a, b in self.INPUT_DATA])
        self.rtl_simulator_cls = None


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = _TestIEEE754FpComparator()

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([IEEE754FpCmp_TC('test_cmp_py')])
    suite = testLoader.loadTestsFromTestCase(IEEE754FpCmp_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
