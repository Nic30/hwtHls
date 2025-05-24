#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from pathlib import Path
from typing import List, Optional, Literal
from unittest import expectedFailure

from hwt.hwModule import HwModule
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeStreamLoopUnroll
from hwtHls.llvm.llvmIr import MachineFunction, LLVMStringContext, Function, LlvmCompilationBundle
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr, LlvmIrInterpretArgs
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axi4s import Axi4StreamFrameUtils
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.io.amba.axi4Stream.axi4sCopyByteByByte import Axi4SPacketCopyByteByByte
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


# from hwtHlsGdb.gdbCmdHandlerLlvmIr import GdbCmdHandlerLllvmIr
# from hwtHlsGdb.gdbServerStub import GDBServerStub
class BaseAxi4SPktInPktOutTC(SimTestCase):
    """
    Base class for tests which test component which takes 1 frame and produces 1 frame
    Input port should be named "rx", output port should be named "tx"
    """
    StreamFrameUtils = Axi4StreamFrameUtils

    def _runLlvmIrInterpret(self, strCtx: LLVMStringContext, f: Function, args: LlvmIrInterpretArgs):
        try:
            with open(Path(self.DEFAULT_LOG_DIR, f"{self.getTestName()}.llvmIrWave.vcd"), "w") as vcdFile:
                waveLog = VcdWriter(vcdFile)
                interpret = LlvmIrInterpret(f, strCtx)
                interpret.installWaveLog(waveLog)
                # gdbLlvmIrHandler = GdbCmdHandlerLllvmIr(interpret, args)
                # gdbServer = GDBServerStub(gdbLlvmIrHandler)
                # gdbServer.start()
                interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed

    @staticmethod
    def _packFrames(fu: Axi4StreamFrameUtils, frames: list[int]):
        dataIn = []
        for frame in frames:
            frameBeats = fu.pack_frame(frame)
            dataIn.extend(fu.concatWordBits(frameBeats))
        return dataIn

    def _testLlvmIr(self, dut: Axi4SPacketCopyByteByByte,
                    strCtx: LLVMStringContext, f: Function, refFramesIn: List[List[int]], refFramesOut: List[List[int]]):
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        dataIn = self._packFrames(rxFu, refFramesIn)

        dataOut = []
        args = [iter(dataIn), dataOut]
        self._runLlvmIrInterpret(strCtx, f, args)

        DW = dut.OUT_DATA_WIDTH
        LAST_OFFSET = DW + DW // 8
        dataOut = deque((d[DW:], d[LAST_OFFSET:DW], d[LAST_OFFSET]) for d in dataOut)
        # for d in dataOut:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))

        txFu = self.StreamFrameUtils.from_HwIO(dut.tx)
        for frame in refFramesOut:
            offset, data = txFu.receive_bytes(dataOut)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)

        self.assertEqual(len(dataOut), 0)

    def _testLlvmMir(self, dut: Axi4SPacketCopyByteByByte, strCtx: LLVMStringContext, mf: MachineFunction, refFramesIn: List[List[int]], refFramesOut: List[List[int]]):
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        dataIn = self._packFrames(rxFu, refFramesIn)

        dataOut = []
        args = [iter(dataIn), dataOut]
        interpret = LlvmMirInterpret(mf, strCtx)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        DW = dut.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        txFu = self.StreamFrameUtils.from_HwIO(dut.tx)

        for frame in refFramesOut:
            offset, data = txFu.receive_bytes(dataOut)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)

        self.assertEqual(len(dataOut), 0)

    def _testRtl(self, dut: HwModule, freq:int, rtlSimTimeMultiplier:float,
                  refFramesIn: List[List[int]], refFramesOut: List[List[int]],
                ):
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        for refFrame in refFramesIn:
            rxFu.send_bytes(refFrame, dut.rx._ag.data)

        t = int(freq_to_period(freq) * (len(dut.rx._ag.data) + 10) * rtlSimTimeMultiplier)
        self.runSim(t)
        txFu = self.StreamFrameUtils.from_HwIO(dut.tx)
        for frame in refFramesOut:
            offset, data = txFu.receive_bytes(dut.tx._ag.data)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)

        self.assertEqual(len(dut.tx._ag.data), 0)

    def _test(self, dut: HwModule, refFramesIn: List[List[int]], refFramesOut: List[List[int]], freq=int(1e6),
              rtlSimTimeMultiplier=2.0,
              platformKwargs=dict(
                  # debugFilter={*HlsDebugBundle.ALL_RELIABLE,
                  # HlsDebugBundle.DBG_20_addSignalNamesToSync,
                  # HlsDebugBundle.DBG_20_addSignalNamesToData,
                  # },
                  # llvmCliArgs=[
                  # # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                  # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                  # ],
                  # runTestAfterEachPass=True,
                  # runTestAfterEachIrPass=True,
                  # runTestAfterEachMirPass=True,
              )
              ):
        """
        test LLVM IR, MIR and RTL
        """
        dut.CLK_FREQ = freq
        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.strCtx, llvm.main, refFramesIn, refFramesOut)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.strCtx, llvm.getMachineFunction(llvm.main), refFramesIn, refFramesOut)

        platform = TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr,
            optMirTest=testLlvmOptMir,
            **platformKwargs)
        self.compileSimAndStart(dut, target_platform=platform)

        self._testRtl(dut, freq, rtlSimTimeMultiplier, refFramesIn, refFramesOut,)


class Axi4SPacketCopyByteByByteTC(BaseAxi4SPktInPktOutTC):

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH:int, FRAME_LENGTHS:List[int],
        UNROLL:Optional[Literal[PyBytecodeStreamLoopUnroll]]=None, freq=int(1e6),
        rtlSimTimeMultiplier=2.0,
        cls=Axi4SPacketCopyByteByByte):

        dut = cls()
        dut.UNROLL = UNROLL
        dut.DATA_WIDTH = DATA_WIDTH
        dut.OUT_DATA_WIDTH = OUT_DATA_WIDTH

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        BaseAxi4SPktInPktOutTC._test(self, dut, refFrames, refFrames, freq=freq,
                                     rtlSimTimeMultiplier=rtlSimTimeMultiplier)

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

    # [todo] mir does not produce any packets
    # def test_4B(self):
    #     PKT_CNT = 6
    #     self._test(4 * 8, 4 * 8, [self._rand.randint(1, 12) for _ in range(PKT_CNT)])

    def _testUnrollForEx(self, WORD_BYTE_CNT:int, PKT_CNT=6):
        self._test(WORD_BYTE_CNT * 8, WORD_BYTE_CNT * 8, [self._rand.randint(1, WORD_BYTE_CNT * 3) for _ in range(PKT_CNT)], UNROLL=PyBytecodeStreamLoopUnroll)

    def test_1B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForEx(1)

    def test_2B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForEx(2)

    def test_3B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForEx(3)

    def test_4B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForEx(4)

    def test_16B_PyBytecodeStreamLoopUnroll_forRx(self):
        self._testUnrollForEx(16)

    # :todo: unroll before stream lowering otherwise code explodes
    @expectedFailure
    def test_2B_unroll2(self):
        PKT_CNT = 6
        self._test(2 * 8, 2 * 8, [self._rand.randint(1, 6) for _ in range(PKT_CNT)],
                   UNROLL=PyBytecodeLLVMLoopUnroll(True, 2),
                   rtlSimTimeMultiplier=3)

    @expectedFailure
    def test_4B_unroll2(self):
        PKT_CNT = 6
        self._test(4 * 8, 4 * 8, [self._rand.randint(1, 12) for _ in range(PKT_CNT)],
                   UNROLL=PyBytecodeLLVMLoopUnroll(True, 2),
                   rtlSimTimeMultiplier=4)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.virtual import VirtualHlsPlatform
    m = Axi4SPacketCopyByteByByte()
    m.UNROLL = PyBytecodeStreamLoopUnroll  # PyBytecodeLLVMLoopUnroll(True, 2)
    # m.UNROLL = PyBytecodeLLVMLoopUnroll(True, 2)
    # m.UNROLL = None
    m.DATA_WIDTH = 2 * 8
    m.OUT_DATA_WIDTH = 2 * 8
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter={
      *HlsDebugBundle.ALL_RELIABLE,
      # HlsDebugBundle.DBG_20_addSignalNamesToSync
    },
    llvmCliArgs=[
        # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
        # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
       ],
    )
    # print(to_rtl_str(m, target_platform=p))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([Axi4SPacketCopyByteByByteTC("test_2B_unroll2")])
    suite = testLoader.loadTestsFromTestCase(Axi4SPacketCopyByteByByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
