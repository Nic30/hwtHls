#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from pathlib import Path
from typing import List

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.llvm.llvmIr import MachineFunction, LLVMStringContext, Function, LlvmCompilationBundle
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axis import axis_send_bytes, packAxiSFrame, \
    _axis_recieve_bytes, axis_recieve_bytes
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.io.amba.axiStream.axisCopyByteByByte import AxiSPacketCopyByteByByte
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform
# from hwtHlsGdb.gdbCmdHandlerLlvmIr import GdbCmdHandlerLllvmIr
# from hwtHlsGdb.gdbServerStub import GDBServerStub


class AxiSPacketCopyByteByByteTC(SimTestCase):

    def _testLlvmIr(self, u: AxiSPacketCopyByteByByte,
                    strCtx: LLVMStringContext, f: Function, refFrames: List[List[int]]):
        dataIn = []
        strbT = Bits(u.DATA_WIDTH // 8)
        for refFrame in refFrames:
            # print(refFrame)
            t = uint8_t[len(refFrame)]
            _data_B = t.from_py(refFrame)
            frameBeats = packAxiSFrame(u.DATA_WIDTH, _data_B, withStrb=True)
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

        DW = u.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        # for d in dataOut:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))

        for frame in refFrames:
            offset, data = _axis_recieve_bytes(dataOut, DW // 8, True, False)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dataOut), 0)

    def _testLlvmMir(self, u: AxiSPacketCopyByteByByte, mf: MachineFunction, refFrames: List[List[int]]):
        dataIn = []
        strbT = Bits(u.DATA_WIDTH // 8)
        for refFrame in refFrames:
            t = uint8_t[len(refFrame)]
            _data_B = t.from_py(refFrame)
            frameBeats = packAxiSFrame(u.DATA_WIDTH, _data_B, withStrb=True)
            dataIn.extend(Concat(BIT.from_py(last), strbT.from_py(strb), data) for data, strb, last in frameBeats)

        dataOut = []
        args = [iter(dataIn), dataOut]
        interpret = LlvmMirInterpret(mf)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        DW = u.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        for frame in refFrames:
            offset, data = _axis_recieve_bytes(dataOut, DW // 8, True, False)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dataOut), 0)

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH: int, FRAME_LENGTHS: List[int], freq=int(1e6)):
        u = AxiSPacketCopyByteByByte()
        u.UNROLL = None
        u.DATA_WIDTH = DATA_WIDTH
        u.OUT_DATA_WIDTH = OUT_DATA_WIDTH
        u.CLK_FREQ = freq

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(u, llvm.strCtx, llvm.main, refFrames)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(u, llvm.getMachineFunction(llvm.main), refFrames)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform(optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir, debugFilter=HlsDebugBundle.ALL_RELIABLE))

        for refFrame in refFrames:
            axis_send_bytes(u.rx, refFrame)

        t = int(freq_to_period(freq)) * (len(u.rx._ag.data) + 10) * 2
        self.runSim(t)

        for frame in refFrames:
            offset, data = axis_recieve_bytes(u.txBody)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(u.txBody._ag.data), 0)

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
    from hwt.synthesizer.utils import to_rtl_str
    u = AxiSPacketCopyByteByByte()
    u.UNROLL = None
    u.DATA_WIDTH = 1 * 8
    u.OUT_DATA_WIDTH = 2 * 8
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(u, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([AxiSPacketCopyByteByByteTC("test_4B")])
    suite = testLoader.loadTestsFromTestCase(AxiSPacketCopyByteByByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
