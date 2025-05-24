#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.llvm.llvmIr import LLVMStringContext, Function, LlvmCompilationBundle, \
    MachineFunction
from hwtHls.ssa.analysis.llvmIrInterpret import SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axi4s import Axi4StreamFrameUtils
from hwtSimApi.utils import freq_to_period
from tests.io.amba.axi4Stream.axi4sCopyByteByByte_test import Axi4SPacketCopyByteByByteTC
from tests.io.amba.axi4Stream.axi4sPacketByteCntr import Axi4SPacketByteCntr0, Axi4SPacketByteCntr1, \
    Axi4SPacketByteCntr2, Axi4SPacketByteCntr3
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class _Axi4SPacketByteCntrTC(SimTestCase):
    _Axi4StreamFrameUtils = Axi4StreamFrameUtils

    @override
    def _generateFramesFromLens(self, dut: Axi4SPacketByteCntr0, LENS: List[int]):
        dataIn = []
        fu = self._Axi4StreamFrameUtils.from_HwIO(dut.i)
        for LEN in LENS:
            frameBeats = []
            fu.send_bytes(list(range(LEN)), frameBeats)
            dataIn.extend(fu.concatWordBits(frameBeats))

        return dataIn

    def _checkResults(self, SUM_ONLY:bool, LENS: List[int], dataOut: List[HBitsConst]):
        if SUM_ONLY:
            self.assertValEqual(dataOut[-1], sum(LENS))
        else:
            self.assertValSequenceEqual(dataOut, LENS)

    def _testLlvmIr(self, dut: Axi4SPacketByteCntr0,
                    strCtx: LLVMStringContext, f: Function, SUM_ONLY:bool, LENS: List[int]):
        dataIn = self._generateFramesFromLens(dut, LENS)
        dataOut = []
        args = [dataOut, iter(dataIn)]
        try:
            Axi4SPacketCopyByteByByteTC._runLlvmIrInterpret(self, strCtx, f, args)
        except NotImplementedError:
            return  # skip cases with hwtHls.streamRead and alike

        self._checkResults(SUM_ONLY, LENS, dataOut)

    def _testLlvmMir(self, dut: Axi4SPacketByteCntr0, strCtx: LLVMStringContext, mf: MachineFunction, SUM_ONLY:bool, LENS: List[int]):
        dataIn = self._generateFramesFromLens(dut, LENS)
        dataOut = []
        args = [dataOut, iter(dataIn)]
        interpret = LlvmMirInterpret(mf, strCtx)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed

        self._checkResults(SUM_ONLY, LENS, dataOut)

    def _run_test_byte_cnt(self, dut: Axi4SPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False):
        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.strCtx, llvm.main, SUM_ONLY, LENS)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.strCtx, llvm.getMachineFunction(llvm.main), SUM_ONLY, LENS)

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
        fu = self._Axi4StreamFrameUtils.from_HwIO(dut.i)
        for LEN in LENS:
            fu.send_bytes(list(range(LEN)), dut.i._ag.data)

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * T_MUL
        self.runSim(t)
        self.assertEmpty(dut.i._ag.data)
        self._checkResults(SUM_ONLY, LENS, dut.byte_cnt._ag.data)


class Axi4SPacketByteCntrTC(_Axi4SPacketByteCntrTC):

    def _test_byte_cnt(self, DATA_WIDTH:int, SEGMENT_CNT:int=1, cls=Axi4SPacketByteCntr0, LENS=[1, 2, 3, 4], T_MUL=1, CLK_FREQ=int(1e6),
                       SUM_ONLY:bool=True, TEST_IR:bool=False, TEST_MIR:bool=False):
        dut = cls()
        assert SEGMENT_CNT == 1, SEGMENT_CNT
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = CLK_FREQ
        self._run_test_byte_cnt(dut, LENS, T_MUL, CLK_FREQ, SUM_ONLY, TEST_IR, TEST_MIR)

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
    m = Axi4SPacketByteCntr3()
    m.CLK_FREQ = int(1e6)
    m.DATA_WIDTH = 48
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketByteCntrTC("test_Axi4SPacketByteCntr3_48b")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketByteCntrTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
