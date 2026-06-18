#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from tests.io.amba.axi4Stream.axi4sPacketByteCntr import Axi4SPacketByteCntr0, Axi4SPacketByteCntr1, \
    Axi4SPacketByteCntr2, Axi4SPacketByteCntr3
from tests.passTestIo import PassTestIoOut
from tests.passTestIoStream import PassTestIoInStream
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule


class PassTestIoOutTestOnlyFinalSum(PassTestIoOut):

    @override
    def checkForLlvmIr(self, dataSim:list[HBitsConst]):
        self.passTests.tc.assertValEqual(dataSim[-1], sum(self.dataRef))

    @override
    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        dataSim = oPort._ag.data
        self.passTests.tc.assertValEqual(dataSim[-1], sum(self.dataRef))


class _Axi4SPacketByteCntrTC(SimTestCase):
    _Axi4StreamSimFrameUtils = Axi4StreamSimFrameUtils

    def _run_test_byte_cnt(self, dut: Axi4SPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1,
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False, platformKwargs=dict(
                           # debugFilter={ #*HlsDebugBundle.ALL_RELIABLE,
                           #              # HlsDebugBundle.DBG_20_addSignalNamesToSync,
                           #              # HlsDebugBundle.DBG_20_addSignalNamesToData,
                           #              },
                           # runTestAfterEachPass=True
                           )):
        dataIn = []
        for LEN in LENS:
            dataIn.append(list(range(LEN)))
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.bindDataByInOut((PassTestIoInStream(self._Axi4StreamSimFrameUtils, dataIn),),
                                  (PassTestIoOutTestOnlyFinalSum(LENS) if SUM_ONLY else PassTestIoOut(LENS),),
                                  PORT_NAMES=("i", "o_byte_cnt"))
        passTests.setRunTestsAfter(runTestBeforeLlvmIrPasses=False, runTestAfterIrPasses=TEST_IR, runTestAfterMirPasses=TEST_MIR)
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=T_MUL)
        passTests.test_allInOne(platformKwArgs=platformKwargs)


class Axi4SPacketByteCntrTC(_Axi4SPacketByteCntrTC):

    def _test_byte_cnt(self, DATA_WIDTH:int, SEGMENT_CNT:int=1, cls=Axi4SPacketByteCntr0,
                       LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False):
        dut = cls()
        assert SEGMENT_CNT == 1, SEGMENT_CNT
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        self._run_test_byte_cnt(dut, LENS=LENS, T_MUL=T_MUL, SUM_ONLY=SUM_ONLY, TEST_IR=TEST_IR, TEST_MIR=TEST_MIR)

    def test_Axi4SPacketByteCntr0_8b(self):
        self._test_byte_cnt(8)

    def test_Axi4SPacketByteCntr0_16b(self):
        self._test_byte_cnt(16)

    def test_Axi4SPacketByteCntr0_24b(self):
        self._test_byte_cnt(24)

    def test_Axi4SPacketByteCntr0_48b(self):
        self._test_byte_cnt(48)

    def test_Axi4SPacketByteCntr1_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr1_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr1)

    def test_Axi4SPacketByteCntr2_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr2)

    def test_Axi4SPacketByteCntr2_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr2)

    def test_Axi4SPacketByteCntr2_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr2)

    def test_Axi4SPacketByteCntr2_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr2)

    def test_Axi4SPacketByteCntr3_8b(self):
        self._test_byte_cnt(8, cls=Axi4SPacketByteCntr3, SUM_ONLY=False, TEST_IR=True, TEST_MIR=True)

    def test_Axi4SPacketByteCntr3_16b(self):
        self._test_byte_cnt(16, cls=Axi4SPacketByteCntr3, SUM_ONLY=False, TEST_IR=True, TEST_MIR=True)

    def test_Axi4SPacketByteCntr3_24b(self):
        self._test_byte_cnt(24, cls=Axi4SPacketByteCntr3, SUM_ONLY=False, TEST_IR=True, TEST_MIR=True)

    def test_Axi4SPacketByteCntr3_48b(self):
        self._test_byte_cnt(48, cls=Axi4SPacketByteCntr3, SUM_ONLY=False, TEST_IR=True, TEST_MIR=True)


if __name__ == '__main__':
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.virtual import VirtualHlsPlatform
    m = Axi4SPacketByteCntr0()
    m.CLK_FREQ = int(1e6)
    m.DATA_WIDTH = 16
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketByteCntrTC)
    # suite = unittest.TestSuite([Axi4SPacketByteCntrTC("test_Axi4SPacketByteCntr0_16b")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
