#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from pathlib import Path
from typing import List

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.llvm.llvmIr import Function, MachineFunction, LLVMStringContext
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.axisDetectIoAccessGraph import SsaAnalysisAxisDetectIoAccessGraph
from hwtHls.ssa.analysis.axisDetectReadStatements import SsaAnalysisAxisDetectReadStatements
from hwtHls.ssa.analysis.llvmMirInterpret import runLlvmMachineFunction, \
    SimIoUnerflowErr
from hwtHlsGdb.gdbCmdHandlerLlvmIr import GdbCmdHandlerLllvmIr
from hwtHlsGdb.gdbServerStub import GDBServerStub
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.amba.axis import AxiStream, axis_send_bytes, packAxiSFrame, \
    _axis_recieve_bytes, axis_recieve_bytes
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.utils import freq_to_period
from ipCorePackager.constants import DIRECTION
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.baseSsaTest import TestFinishedSuccessfuly
from tests.io.amba.axiStream.axisCopyByteByByte import AxiSPacketCopyByteByByte
from hwtHls.ssa.analysis.llvmIrInterpret import runLlvmIrFunction


# from hwtHls.ssa.analysis.llvmIrInterpret import runLlvmIrFunction
class AxiSPacketCopyByteByByteTC(SimTestCase):

    def _test_read_offsets(self, DATA_WIDTH:int, CLK_FREQ=int(1e6)):
        u = AxiSPacketCopyByteByByte()
        u.DATA_WIDTH = DATA_WIDTH
        u.CLK_FREQ = CLK_FREQ
        tc = self

        class CheckOffsets(SsaPass):

            def apply(self, hls:"HlsScope", toSsa: HlsAstToSsa):
                rStms: SsaAnalysisAxisDetectReadStatements = toSsa.getAnalysis(SsaAnalysisAxisDetectReadStatements)
                tc.assertEqual(len(rStms.intfs), 1)
                tc.assertEqual(len(rStms.ios), 3)

                for intf in rStms.intfs:
                    intf: AxiStream
                    intfCfg: SsaAnalysisAxisDetectIoAccessGraph = toSsa.getAnalysis(SsaAnalysisAxisDetectIoAccessGraph(
                        toSsa, intf, DIRECTION.IN))
                    cfg, startBlock = intfCfg.cfg, intfCfg.startBlock
                    tc.assertEqual(len(cfg.allStms), 3)

                    start, read, end = cfg.allStms
                    tc.assertIsInstance(start, HlsStmReadStartOfFrame)
                    tc.assertIsInstance(read, HlsStmReadAxiStream)
                    tc.assertIsInstance(end, HlsStmReadEndOfFrame)

                    tc.assertIn(start, cfg.predecessors.keys())
                    tc.assertIn(read, cfg.predecessors.keys())
                    tc.assertIn(end, cfg.predecessors.keys())
                    tc.assertSequenceEqual(cfg.predecessors[start], [None])
                    tc.assertSequenceEqual(cfg.predecessors[read], [start, read])
                    tc.assertSequenceEqual(cfg.predecessors[end], [read])
                    tc.assertDictEqual(cfg.inWordOffset,
                                       {
                                           None: [0],
                                           start: [0],
                                           read: list(range(0, DATA_WIDTH, 8)),
                                           end: list(range(0, DATA_WIDTH, 8)),
                                        })
                    raise TestFinishedSuccessfuly()

        class TestVirtualHlsPlatform(VirtualHlsPlatform):

            def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
                CheckOffsets().apply(hls, toSsa)
                raise AssertionError("Should never get there")

        with self.assertRaises(TestFinishedSuccessfuly):
            self.compileSimAndStart(u, target_platform=TestVirtualHlsPlatform())

    def test_1B_read_offsets(self):
        self._test_read_offsets(8)

    def test_2B_read_offsets(self):
        self._test_read_offsets(2 * 8)

    def test_3B_read_offsets(self):
        self._test_read_offsets(3 * 8)

    def test_4B_read_offsets(self):
        self._test_read_offsets(4 * 8)

    #def _testLlvmIr(self, u: AxiSPacketCopyByteByByte, strCtx: LLVMStringContext, f: Function, refFrames: List[List[int]]):
    #    dataIn = []
    #    strbT = Bits(u.DATA_WIDTH // 8)
    #    for refFrame in refFrames:
    #        #print(refFrame)
    #        t = uint8_t[len(refFrame)]
    #        _data_B = t.from_py(refFrame)
    #        frameBeats = packAxiSFrame(u.DATA_WIDTH, _data_B, withStrb=True)
    #        dataIn.extend(Concat(BIT.from_py(last), strbT.from_py(strb), data) for data, strb, last in frameBeats)
    #
    #    dataOut = []
    #    args = [iter(dataIn), dataOut]
    #    try:
    #        with open(Path(self.DEFAULT_LOG_DIR, f"{self.getTestName()}.llvmIrWave.vcd"), "w") as vcdFile:
    #            waveLog = VcdWriter(vcdFile)
    #        #    gdbLlvmIrHandler = GdbCmdHandlerLllvmIr(strCtx, f, args, waveLog)
    #        #    gdbServer = GDBServerStub(gdbLlvmIrHandler)
    #        #    gdbServer.start()
    #            runLlvmIrFunction(strCtx, f, args, waveLog=waveLog)
    #    except SimIoUnerflowErr:
    #        pass  # all inputs consumed
    #
    #    DW = u.OUT_DATA_WIDTH
    #    dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
    #    #for d in dataOut:
    #    #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
    #    #    print(' '.join(d))
    #
    #    for frame in refFrames:
    #        offset, data = _axis_recieve_bytes(dataOut, DW // 8, True, False)
    #        self.assertEqual(offset, 0)
    #        self.assertValSequenceEqual(data, frame)
    #    self.assertEqual(len(dataOut), 0)

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
        try:
            runLlvmMachineFunction(mf, args)
        except SimIoUnerflowErr:
            pass  # all inputs consummed
        DW = u.OUT_DATA_WIDTH
        dataOut = deque((d[DW:], d[(DW + DW // 8):DW], d[DW + DW // 8]) for d in dataOut)
        print(dataOut)
        for frame in refFrames:
            offset, data = _axis_recieve_bytes(dataOut, DW // 8, True, False)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)
        self.assertEqual(len(dataOut), 0)

    def _test(self, DATA_WIDTH:int, OUT_DATA_WIDTH: int, FRAME_LENGTHS: List[int], freq=int(1e6)):
        u = AxiSPacketCopyByteByByte()
        u.DATA_WIDTH = DATA_WIDTH
        u.OUT_DATA_WIDTH = OUT_DATA_WIDTH
        u.CLK_FREQ = freq

        refFrames = []
        for frameLen in FRAME_LENGTHS:
            data = [i for i in range(1, frameLen + 1)]
            # data = [self._rand.getrandbits(8) for _ in range(frameLen)]
            refFrames.append(data)

        tc = self

        class TestVirtualHlsPlatform(VirtualHlsPlatform):

            #def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
            #    res = super(TestVirtualHlsPlatform, self).runSsaPasses(hls, toSsa)
            #    tr: ToLlvmIrTranslator = toSsa.start
            #    tc._testLlvmIr(u, tr.llvm.strCtx, tr.llvm.main, refFrames)
            #    return res

            def runNetlistTranslation(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa,
                              mf: MachineFunction, *args):
                tr: ToLlvmIrTranslator = toSsa.start
                tc._testLlvmMir(u, tr.llvm.getMachineFunction(tr.llvm.main), refFrames)
                netlist = super(TestVirtualHlsPlatform, self).runNetlistTranslation(hls, toSsa, mf, *args)
                return netlist

        self.compileSimAndStart(u, target_platform=TestVirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE))

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

    import unittest
    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([AxiSPacketCopyByteByByteTC("test_2B")])
    # suite = testLoader.loadTestsFromTestCase(AxiSPacketCopyByteByByteTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
