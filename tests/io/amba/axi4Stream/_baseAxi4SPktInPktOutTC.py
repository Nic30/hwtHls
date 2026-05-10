#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from typing import Optional

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC, LlvmSimFunctionArgT
from tests.io.amba.axi4Stream.axi4sCopyByteByByte import Axi4SPacketCopyByteByByte
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


# from hwtHlsGdb.gdbCmdHandlerLlvmIr import GdbCmdHandlerLllvmIr
# from hwtHlsGdb.gdbServerStub import GDBServerStub
class BaseAxi4SPktInPktOutTC(BaseIrMirRtl_TC):
    """
    Base class for tests which test component which takes 1 frame and produces 1 frame
    Input port should be named "rx", output port should be named "tx"
    """
    StreamFrameUtils = Axi4StreamSimFrameUtils

    @staticmethod
    def _packFrames(fu: Axi4StreamSimFrameUtils, frames: list[int]):
        dataIn = []
        for frame in frames:
            fu.send_bytes(frame, dataIn)
        res = fu.concatWordBits(dataIn)
        return res

    def _testLlvmIrOrMir(self, platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator,
                         variantName: str, wallTime:Optional[int], isMir: bool,
                         refFramesIn: list[list[int]], refFramesOut: list[list[int]]):
        dut: Axi4SPacketCopyByteByByte = toLlvm.parentHwModule
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        dataIn = self._packFrames(rxFu, refFramesIn)

        tx = []
        args: LlvmSimFunctionArgT = [iter(dataIn), tx]
        self._runLlvmIrOrMir(platform, toLlvm, variantName, wallTime, isMir, args)

        txFu = self.StreamFrameUtils.from_HwIO(dut.tx)
        tx = deque(txFu.updackWordBits(d) for d in tx)
        # for d in tx:
        #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
        #    print(' '.join(d))

        for frame in refFramesOut:
            offset, data = txFu.receive_bytes(tx)
            self.assertEqual(offset, 0)
            self.assertValSequenceEqual(data, frame)

        self.assertEqual(len(tx), 0)

    def _testRtl(self, dut: HwModule, freq:int, rtlSimTimeMultiplier:float,
                  refFramesIn: list[list[int]], refFramesOut: list[list[int]],
                ):
        dut.rx._ag.presetBeforeClk = True
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

    @override
    def _test(self, dut: HwModule, refFramesIn: list[list[int]], refFramesOut: list[list[int]], freq=int(1e6),
              rtlSimTimeMultiplier=2.0,
              platformArgs=(),
              platformKwargs=dict(
                  debugFilter={  # *HlsDebugBundle.ALL_RELIABLE,
                  # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                  # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                   },
                   llvmCliArgs=[
                      # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                      # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                      # LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL
                   ],
                  # runTestAfterEachPass=True,
                  # runTestAfterEachIrPass=True,
                  # runTestAfterEachMirPass=True,
              ),
              testLlvmIrNoOpt=NOT_SPECIFIED,
              testLlvmIr=NOT_SPECIFIED,
              testLlvmMir=NOT_SPECIFIED,
              ):
        """
        test LLVM IR, MIR and RTL
        """
        dut.CLK_FREQ = freq

        tc = self
        wallTimeIr = None
        wallTimeOptIr = None
        wallTimeOptMir = None
        if testLlvmIrNoOpt is NOT_SPECIFIED:

            def testLlvmIrNoOpt(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator):
                tc._testLlvmIrOrMir(platform, toLlvm, "", wallTimeIr, False, refFramesIn, refFramesOut)

        if testLlvmIr is NOT_SPECIFIED:

            def testLlvmIr(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator):
                tc._testLlvmIrOrMir(platform, toLlvm, "opt", wallTimeOptIr, False, refFramesIn, refFramesOut)

        if testLlvmMir is NOT_SPECIFIED:

            def testLlvmMir(platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator):
                tc._testLlvmIrOrMir(platform, toLlvm, "", wallTimeOptMir, True, refFramesIn, refFramesOut)

        target_platform = TestLlvmIrAndMirPlatform(
            topToRunTestsOn=dut,
            noOptIrTest=testLlvmIrNoOpt,
            optIrTest=testLlvmIr,
            optMirTest=testLlvmMir,
            *platformArgs, **platformKwargs)
        self.compileSimAndStart(dut, target_platform=target_platform)
        self._test_no_comb_loops()
        self._testRtl(dut, freq, rtlSimTimeMultiplier, refFramesIn, refFramesOut)


class BaseAxi4SPktInScalarOutTC(BaseAxi4SPktInPktOutTC):

    def assertLlvmIrOrMirEqual(self, tx, refTx):
        self.assertValSequenceEqual(tx, refTx)

    @override
    def _testLlvmIrOrMir(self, platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator,
                         variantName: str, wallTime:Optional[int], isMir: bool,
                         refFramesIn: list[list[int]], refOut: list[int]):
        dut: Axi4SPacketCopyByteByByte = toLlvm.parentHwModule
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        dataIn = self._packFrames(rxFu, refFramesIn)

        tx = []
        args = [iter(dataIn), tx]
        self._runLlvmIrOrMir(platform, toLlvm, variantName, wallTime, isMir, args)
        self.assertLlvmIrOrMirEqual(tx, refOut)

    @override
    def _testRtl(self, dut: HwModule, freq:int, rtlSimTimeMultiplier:float,
                  refFramesIn: list[list[int]], refOut: list[HBitsConst],
                ):
        dut.rx._ag.presetBeforeClk = True
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        for refFrame in refFramesIn:
            rxFu.send_bytes(refFrame, dut.rx._ag.data)

        t = int(freq_to_period(freq) * (len(dut.rx._ag.data) + 10) * rtlSimTimeMultiplier)
        self.runSim(t)

        self.assertValSequenceEqual(dut.tx._ag.data, refOut)


class BaseAxi4SPkt1RxManyTxTC(BaseAxi4SPktInPktOutTC):

    def _testLlvmIrOrMir(self, platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator,
                         variantName: str, wallTime:Optional[int], isMir: bool,
                         refFramesIn: list[list[int]], refFramesOuts: list[tuple[list[int], ...]]):
        dut: Axi4SPacketCopyByteByByte = toLlvm.parentHwModule
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        dataIn = self._packFrames(rxFu, refFramesIn)
        assert len(dut.tx) == len(refFramesOuts)

        txs = [[] for _ in len(dut.tx)]
        args: LlvmSimFunctionArgT = [iter(dataIn), *txs]
        self._runLlvmIrOrMir(platform, toLlvm, variantName, wallTime, isMir, args)

        assert len(txs) == len(refFramesOuts)
        for txI, (tx, refFramesOut) in enumerate(zip(txs, refFramesOuts)):
            txFu = self.StreamFrameUtils.from_HwIO(dut.tx[txI])

            tx = deque(txFu.updackWordBits(d) for d in tx)
            # for d in tx:
            #    d = ["%x" % int(_d) if _d._is_full_valid() else repr(_d) for _d in d]
            #    print(' '.join(d))

            for frameI, frame in enumerate(refFramesOut):
                offset, data = txFu.receive_bytes(tx)
                self.assertEqual(offset, 0, ("tx", txI, "frame", frameI))
                self.assertValSequenceEqual(data, frame, ("tx", txI, "frame", frameI))

            self.assertEqual(len(tx), 0, ("tx", txI))

    def _testRtl(self, dut: HwModule, freq:int, rtlSimTimeMultiplier:float,
                  refFramesIn: list[list[int]], refFramesOuts: list[tuple[list[int], ...]],
                ):
        dut.rx._ag.presetBeforeClk = True
        rxFu = self.StreamFrameUtils.from_HwIO(dut.rx)
        for refFrame in refFramesIn:
            rxFu.send_bytes(refFrame, dut.rx._ag.data)

        t = int(freq_to_period(freq) * (len(dut.rx._ag.data) + 10) * rtlSimTimeMultiplier)
        self.runSim(t)
        assert len(dut.tx) == len(refFramesOuts)
        for txI, (tx, refFramesOut) in enumerate(zip(dut.tx, refFramesOuts)):
            txFu = self.StreamFrameUtils.from_HwIO(tx)
            for frameI, frame in enumerate(refFramesOut):
                offset, data = txFu.receive_bytes(tx._ag.data)
                self.assertEqual(offset, 0, ("tx", txI, "frame", frameI))
                self.assertValSequenceEqual(data, frame, ("tx", txI, "frame", frameI))

            self.assertEqual(len(tx._ag.data), 0, ("tx", txI))
