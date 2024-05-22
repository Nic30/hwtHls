#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from pathlib import Path
from typing import List

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeStreamLoopUnroll
from hwtHls.llvm.llvmIr import MachineFunction, LLVMStringContext, Function, LlvmCompilationBundle
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axi4s import axi4s_send_bytes, packAxi4SFrame, \
    _axi4s_recieve_bytes, axi4s_recieve_bytes
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.io.amba.axi4Stream.axi4sCopyByteByByte import Axi4SPacketCopyByteByByte
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


# from hwtHlsGdb.gdbCmdHandlerLlvmIr import GdbCmdHandlerLllvmIr
# from hwtHlsGdb.gdbServerStub import GDBServerStub
class Axi4SPacketCopyByteByByteTC(SimTestCase):

    def _testLlvmIr(self, dut: Axi4SPacketCopyByteByByte,
                    strCtx: LLVMStringContext, f: Function, refFrames: List[List[int]]):
        dataIn = []
        strbT = HBits(dut.DATA_WIDTH // 8)
        for refFrame in refFrames:
            # print(refFrame)
            t = uint8_t[len(refFrame)]
            _data_B = t.from_py(refFrame)
            frameBeats = packAxi4SFrame(dut.DATA_WIDTH, _data_B, withStrb=True)
            dataIn.extend(Concat(BIT.from_py(last), strbT.from_py(strb), data) for data, strb, last in frameBeats)

        dataOut = []
        args = [iter(dataIn), dataOut]
        try:
            with open(Path(self.DEFAULT_LOG_DIR, f"{self.getTestName()}.llvmIrWave.vcd"), "w") as vcdFile:
                waveLog = VcdWriter(vcdFile)
                interpret = LlvmIrInterpret(f)
                interpret.installWaveLog(waveLog, strCtx)
                # gdbLlvmIrHandler = GdbCmdHandlerLllvmIr(interpret, args)
                # gdbServer = GDBServerStub(gdbLlvmIrHandler)
                # gdbServer.start()
                interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed

        DW = dut.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        # for d in dataOut:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))

        for frame in refFrames:
            offset, data = _axi4s_recieve_bytes(dataOut, DW // 8, True, False)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dataOut), 0)

    def _testLlvmMir(self, dut: Axi4SPacketCopyByteByByte, mf: MachineFunction, refFrames: List[List[int]]):
        dataIn = []
        strbT = HBits(dut.DATA_WIDTH // 8)
        for refFrame in refFrames:
            t = uint8_t[len(refFrame)]
            _data_B = t.from_py(refFrame)
            frameBeats = packAxi4SFrame(dut.DATA_WIDTH, _data_B, withStrb=True)
            dataIn.extend(Concat(BIT.from_py(last), strbT.from_py(strb), data) for data, strb, last in frameBeats)

        dataOut = []
        args = [iter(dataIn), dataOut]
        interpret = LlvmMirInterpret(mf)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        DW = dut.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        for frame in refFrames:
            offset, data = _axi4s_recieve_bytes(dataOut, DW // 8, True, False)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dataOut), 0)

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH: int, FRAME_LENGTHS: List[int], freq=int(1e6)):
        """
        test optimizer IR, MIR and RTL
        """
        dut = Axi4SPacketCopyByteByByte()
        dut.UNROLL = None
        dut.DATA_WIDTH = DATA_WIDTH
        dut.OUT_DATA_WIDTH = OUT_DATA_WIDTH
        dut.CLK_FREQ = freq

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.strCtx, llvm.main, refFrames)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.getMachineFunction(llvm.main), refFrames)

        platform = TestLlvmIrAndMirPlatform(optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir,
                                            debugFilter={*HlsDebugBundle.ALL_RELIABLE,
                                                          #HlsDebugBundle.DBG_20_addSignalNamesToSync,
                                                          #HlsDebugBundle.DBG_20_addSignalNamesToData,
                                                          },
                                            # runTestAfterEachPass=True
                                            )
        self.compileSimAndStart(dut, target_platform=platform)

        for refFrame in refFrames:
            axi4s_send_bytes(dut.rx, refFrame)

        t = int(freq_to_period(freq)) * (len(dut.rx._ag.data) + 10) * 2
        self.runSim(t)

        for frame in refFrames:
            offset, data = axi4s_recieve_bytes(dut.txBody)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dut.txBody._ag.data), 0)

    def test_1B(self):
        PKT_CNT = 6
        self._test(8, 8, [self._rand.randint(1, 3) for _ in range(PKT_CNT)])

    def test_2B(self):
        PKT_CNT = 6
        self._test(2 * 8, 2 * 8, [self._rand.randint(1, 4) for _ in range(PKT_CNT)])

    def test_2B_to_1B(self):
        PKT_CNT = 6
        self._test(2 * 8, 8, [self._rand.randint(1, 4) for _ in range(PKT_CNT)])

    def test_1B_to_2B(self):
        PKT_CNT = 6
        self._test(8, 2 * 8, [self._rand.randint(1, 4) for _ in range(PKT_CNT)])

    def test_3B(self):
        PKT_CNT = 6
        self._test(3 * 8, 3 * 8, [self._rand.randint(1, 9) for _ in range(PKT_CNT)])

    def test_4B(self):
        PKT_CNT = 6
        self._test(4 * 8, 4 * 8, [self._rand.randint(1, 12) for _ in range(PKT_CNT)])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    m = Axi4SPacketCopyByteByByte()
    m.UNROLL = PyBytecodeStreamLoopUnroll #PyBytecodeLLVMLoopUnroll(True, 2)
    #m.UNROLL = None
    m.DATA_WIDTH = 3 * 8
    m.OUT_DATA_WIDTH = 3 * 8
    m.CLK_FREQ = int(0.1e6)
    p = VirtualHlsPlatform(debugFilter={
        *HlsDebugBundle.ALL_RELIABLE, 
        # 0HlsDebugBundle.DBG_20_addSignalNamesToSync
    })
    print(to_rtl_str(m, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([Axi4SPacketCopyByteByByteTC("test_2B")])
    #suite = testLoader.loadTestsFromTestCase(Axi4SPacketCopyByteByByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    #runner.run(suite)
