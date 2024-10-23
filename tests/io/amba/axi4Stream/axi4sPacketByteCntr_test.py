#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.llvm.llvmIr import LLVMStringContext, Function, LlvmCompilationBundle, \
    MachineFunction
from hwtHls.ssa.analysis.llvmIrInterpret import SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axi4s import axi4s_send_bytes, packAxi4SFrame, \
    concatDataStrbLastFlags
from hwtSimApi.utils import freq_to_period
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import Axi4SPacketCopyByteByByteTC
from tests.io.amba.axi4Stream.axi4sPacketByteCntr import Axi4SPacketByteCntr0, Axi4SPacketByteCntr1, \
    Axi4SPacketByteCntr2, Axi4SPacketByteCntr3
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class Axi4SPacketCntrTC(SimTestCase):

    def _generateFramesFromLens(self, DATA_WIDTH: int, LENS: List[int]):
        dataIn = []
        strbT = HBits(DATA_WIDTH // 8)
        for LEN in LENS:
            frameBeats = packAxi4SFrame(DATA_WIDTH, range(LEN), withStrb=True)
            frameBeats = list(frameBeats)
            dataIn.extend(concatDataStrbLastFlags(frameBeats, strbT))
        return dataIn

    def _checkResults(self, SUM_ONLY:bool, LENS: List[int], dataOut: List[HBitsConst]):
        if SUM_ONLY:
            self.assertValEqual(dataOut[-1], sum(LENS))
        else:
            self.assertValSequenceEqual(dataOut, LENS)

    def _testLlvmIr(self, dut: Axi4SPacketByteCntr0,
                    strCtx: LLVMStringContext, f: Function, SUM_ONLY:bool, LENS: List[int]):
        dataIn = self._generateFramesFromLens(dut.DATA_WIDTH, LENS)
        dataOut = []
        args = [dataOut, iter(dataIn)]
        try:
            Axi4SPacketCopyByteByByteTC._runLlvmIrInterpret(self, strCtx, f, args)
        except NotImplementedError:
            return  # skip cases with hwtHls.streamRead and alike

        self._checkResults(SUM_ONLY, LENS, dataOut)

    def _testLlvmMir(self, dut: Axi4SPacketByteCntr0, mf: MachineFunction, SUM_ONLY:bool, LENS: List[int]):
        dataIn = self._generateFramesFromLens(dut.DATA_WIDTH, LENS)
        dataOut = []
        args = [dataOut, iter(dataIn)]
        interpret = LlvmMirInterpret(mf)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed

        self._checkResults(SUM_ONLY, LENS, dataOut)

    def _test_byte_cnt(self, DATA_WIDTH:int, cls=Axi4SPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False):
        dut = cls()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.strCtx, llvm.main, SUM_ONLY, LENS)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.getMachineFunction(llvm.main), SUM_ONLY, LENS)

        platform = TestLlvmIrAndMirPlatform(optIrTest=testLlvmOptIr if TEST_IR else None, optMirTest=testLlvmOptMir if TEST_MIR else None,
                                            # debugFilter={ #*HlsDebugBundle.ALL_RELIABLE,
                                            #              # HlsDebugBundle.DBG_20_addSignalNamesToSync,
                                            #              # HlsDebugBundle.DBG_20_addSignalNamesToData,
                                            #              },
                                            # runTestAfterEachPass=True
                                            )
        # platform = VirtualHlsPlatform()
        self.compileSimAndStart(dut, target_platform=platform)
        dut.i._ag.presetBeforeClk = True
        # dut.byte_cnt._ag.presetBeforeClk = True

        for LEN in LENS:
            axi4s_send_bytes(dut.i, list(range(LEN)))

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * T_MUL
        self.runSim(t)
        self._checkResults(SUM_ONLY, LENS, dut.byte_cnt._ag.data)

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
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.platform import HlsDebugBundle
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # m = Axi4SPacketByteCntr3()
    # m.CLK_FREQ = int(1e6)
    # m.DATA_WIDTH = 16
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketCntrTC("test_Axi4SPacketByteCntr3_16b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketCntrTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
