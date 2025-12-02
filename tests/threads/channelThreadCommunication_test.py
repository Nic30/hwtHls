#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIODataRdVld, HwIORdVldSync
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pragmaLoop import PyBytecodeLoopFlattenUsingIf
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc, \
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.hwIOMeta import HwIOMeta
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class Wire2Threads(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(16)

    @override
    def hwDeclr(self) -> None:
        with self._hwParamsShared():
            addClkRstn(self)
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()

    @hlsBytecode
    def t0_readInput(self, hls: HlsScope, out: HwIODataRdVld):
        while b1:
            d = hls.read(self.dataIn)
            hls.write(d.data, out, mayBecomeFlushable=False)

    @hlsBytecode
    def t1_writeInput(self, hls: HlsScope, in_: HwIODataRdVld):
        while b1:
            d = hls.read(in_)
            hls.write(d.data, self.dataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        tmp = HwIODataRdVld()
        tmp.DATA_WIDTH = self.DATA_WIDTH
        tmp._name = "tmp"

        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.t0_readInput, hls, tmp))
        hls.addThread(HlsThreadFromPy(hls, self.t1_writeInput, hls, tmp))
        hls.compile()


class Wire2ThreadsErrorChannelConstructedInAdvance(Wire2Threads):

    @override
    def hwImpl(self) -> None:
        tmp = HwIODataRdVld()
        tmp.DATA_WIDTH = self.DATA_WIDTH
        self.tmp = tmp

        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.t0_readInput, hls, tmp))
        hls.addThread(HlsThreadFromPy(hls, self.t1_writeInput, hls, tmp))
        hls.compile()


class SendCounter2Threads(Wire2Threads):

    @hlsBytecode
    def t1_sendCounter(self, hls: HlsScope, cntIn: HwIODataRdVld):
        while b1:
            cntr = self.dataOut.data._dtype.from_py(0)
            end = hls.read(cntIn).data
            while cntr != end:
                hls.write(cntr, self.dataOut, mayBecomeFlushable=False)
                cntr += 1

    @override
    def hwImpl(self) -> None:
        tmp = HwIODataRdVld()
        tmp.DATA_WIDTH = self.DATA_WIDTH
        tmp._name = "tmp"

        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.t0_readInput, hls, tmp))
        hls.addThread(HlsThreadFromPy(hls, self.t1_sendCounter, hls, tmp))
        hls.compile()


class SequentialShifterInOtherThread0(HwModule):
    """
    :note: Version with input sh and data in same channel
    :note: This is highly inefficient example because there are many asynchronous
        sections which has to have lock (computeSectionLock, loop locks) which
        all lock needs to be taken in acount in logic for synchronization of every theread.
        In addition all sections are executed conditionally thus the enable conditions for
        every action is complex on its own.
        And on top of that all this is completly useless (but this is example of exactly this for test purposes)
        as it saves only 1 clock of latency in specific case where F_max is small and 0 appears on input.
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(16)

    @override
    def hwDeclr(self) -> None:
        with self._hwParamsShared():
            addClkRstn(self)
            dataIn = HwIOStructRdVld()
            dataIn.T = HStruct(
                (HBits(self.DATA_WIDTH), "data"),
                (HBits(log2ceil(self.DATA_WIDTH + 1)), "sh"),
            )
            self.dataIn = dataIn
            self.dataOut = HwIODataRdVld()._m()

    @hlsBytecode
    def t0_dispatch(self, hls: HlsScope, toReturn: HwIODataRdVld, toCompute: HwIOStructRdVld, computeSectionLock: HwIORdVldSync):
        while b1:
            hls.read(computeSectionLock)  # acquire lock token
            d = hls.read(self.dataIn).data
            if d.data._eq(0):
                hls.write(None, toReturn, mayBecomeFlushable=False)
            else:
                hls.write(d, toCompute, mayBecomeFlushable=False)

    @hlsBytecode
    def t1_compute(self, hls: HlsScope, in_: HwIOStructRdVld, out_: HwIODataRdVld):
        while b1:
            d = hls.read(in_).data
            while d.sh != 0:
                d.data >>= 1
                d.sh -= 1
                PyBytecodeLoopFlattenUsingIf(mode=PyBytecodeLoopFlattenUsingIf.Mode.CHILD_LOOP_ENTRY_IN_SAME_ITERATION)

            hls.write(d.data, out_, mayBecomeFlushable=False)

    @hlsBytecode
    def t2_mergeReturn(self, hls: HlsScope, fromDispatch: HwIODataRdVld, fromCompute: HwIODataRdVld, computeSectionLock: HwIORdVldSync):
        res_t = self.dataOut.data._dtype
        while b1:
            PyBytecodeBlockLabel("receive")
            d0 = PyBytecodeInPreproc(hls.read(fromDispatch, blocking=False))
            d = res_t.from_py(None)
            if d0.valid:
                PyBytecodeBlockLabel("reiveFromDispatch")
                d = 0
            else:
                PyBytecodeBlockLabel("reiveFromCompute")
                d = hls.read(fromCompute)

            PyBytecodeBlockLabel("return")
            hls.write(None, computeSectionLock, mayBecomeFlushable=False)  # release lock token
            hls.write(d, self.dataOut, mayBecomeFlushable=False)

    @override
    def hwImpl(self) -> None:
        # :note: the channels are not registered on parent unit because we want to construct channels
        #        in HlsScope
        dispatchToCompute = HwIOStructRdVld()
        dispatchToCompute.T = HStruct(
            (HBits(self.DATA_WIDTH), "data"),
            (HBits(log2ceil(self.DATA_WIDTH + 1)), "sh"),
        )
        dispatchToCompute._name = "dispatchToCompute"
        dispatchToReturn = HwIORdVldSync()
        dispatchToReturn._name = "dispatchToReturn"

        computeToReturn = HwIODataRdVld()
        computeToReturn.DATA_WIDTH = self.DATA_WIDTH
        computeToReturn._name = "computeToReturn"

        computeSectionLock = HwIORdVldSync()
        computeSectionLock._name = "computeSectionLock"
        # :attention: without the computeSectionLock the order of return may not be as expected because
        # the t1_compute may be processing data and then new input with sh=0
        # may skip directly to return section.

        # :note: there are many ways how to solve this issue:
        #  * add sequential tag generator to t0 and then in t2 accept only expected tag
        #    (this requires the knowledge of dominance/post-dominance so we can detect places where fork and join should be placed)
        #  * add section lock
        #    (this locks whole section and prevents potential parallelism)
        #  * add tag to input and output data and perform reordering in user of this
        #    (this requires user to implement reordering)

        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.t0_dispatch, hls,
                                      dispatchToReturn, dispatchToCompute, computeSectionLock))
        hls.addThread(HlsThreadFromPy(hls, self.t1_compute, hls,
                                      dispatchToCompute, computeToReturn))
        hls.addThread(HlsThreadFromPy(hls, self.t2_mergeReturn, hls,
                                      dispatchToReturn, computeToReturn, computeSectionLock))

        hls.hwIOMeta[computeSectionLock] = HwIOMeta(mayBecomeBackedge=True, channelInit=(tuple(),))
        hls.compile()


class SequentialShifterInOtherThread1(SequentialShifterInOtherThread0):
    """
    :note: Version with shIn and dataIn with separated sync
    """

    @override
    def hwDeclr(self) -> None:
        with self._hwParamsShared():
            addClkRstn(self)
            self.dataIn = HwIODataRdVld()
            self.dataOut = HwIODataRdVld()._m()
        self.shIn = HwIODataRdVld()
        self.shIn.DATA_WIDTH = log2ceil(self.DATA_WIDTH + 1)

    @hlsBytecode
    def t0_dispatch(self, hls: HlsScope, toReturn: HwIODataRdVld, toCompute: HwIOStructRdVld, computeSectionLock: HwIORdVldSync):
        while b1:
            hls.read(computeSectionLock)  # acquire lock token
            d = hls.read(self.dataIn).data
            sh = hls.read(self.shIn).data
            if d._eq(0):
                hls.write(None, toReturn)
            else:
                v = toCompute.T.from_py(None)
                v.data = d
                v.sh = sh
                hls.write(v, toCompute)


class ChannelThreadCommunicationTC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def test_Wire2Threads(self):
        dut = Wire2Threads()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        inputs = [1, 2, 3, 4]
        dut.dataIn._ag.data.extend(inputs)
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))
        self.runSim((len(inputs) + 1) * CLK_PERIOD)

        self._test_no_comb_loops()
        self.assertValSequenceEqual(dut.dataOut._ag.data, inputs)

    def test_Wire2ThreadsErrorChannelConstructedInAdvance(self):
        dut = Wire2ThreadsErrorChannelConstructedInAdvance()
        with self.assertRaises(AssertionError):
            self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

    def test_SendCounter2Threads(self):
        dut = SendCounter2Threads()
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        inputs = [1, 2, 3, 4]
        dut.dataIn._ag.data.extend(inputs)
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))
        results = []
        for i in inputs:
            for i2 in range(i):
                results.append(i2)
        self.runSim((len(results) + 2) * CLK_PERIOD)

        self._test_no_comb_loops()
        self.assertValSequenceEqual(dut.dataOut._ag.data, results)

    def test_SequentialShifterInOtherThread0(self, N=7):
        dut = SequentialShifterInOtherThread0()
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))

        expected = []
        all1 = mask(8)
        up1 = mask(7) << 1
        inputs = [(all1 if i < 3 else up1, i) for i in range(N)]

        def model():
            inIt = iter(inputs)
            while True:
                i, sh = next(inIt)
                yield int(i >> sh)

        m = model()
        for _ in range(N):
            expected.append(next(m))

        dut.dataIn._ag.data.extend(inputs)
        self.runSim((sum(i + 1 for i in range(N)) + 1) * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, expected)

    def test_SequentialShifterInOtherThread1(self, N=7):
        dut = SequentialShifterInOtherThread1()
        dut.CLK_FREQ = int(1e6)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform(
            # debugFilter={*HlsDebugBundle.ALL_RELIABLE,
            #          HlsDebugBundle.DBG_5_0_hwtHlsStats,
            #          HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
            #          HlsDebugBundle.DBG_4_0_addSignalNamesToData,
            #          # HlsDebugBundle.DBG_4_4_syncLoweringAbc,
            #          # HlsDebugBundle.DBG_4_4_syncLoweringNodes,
            #          },
            ))
        CLK_PERIOD = int(freq_to_period(dut.CLK_FREQ))

        expected = []
        all1 = mask(8)
        up1 = mask(7) << 1
        inputData = []
        inputShift = []
        for sh in range(N):
            d = all1 if sh < 3 else up1
            inputData.append(d)
            inputShift.append(sh)

        def model():
            inIt = iter(zip(inputData, inputShift))
            while True:
                i, sh = next(inIt)
                yield int(i >> sh)

        m = model()
        for _ in range(N):
            expected.append(next(m))

        dut.dataIn._ag.data.extend(inputData)
        dut.shIn._ag.data.extend(inputShift)
        self.runSim((sum(i + 1 for i in range(N)) + 1) * CLK_PERIOD)
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.dataOut._ag.data, expected)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    # m = SequentialShifterInOtherThread1()
    # m.CLK_FREQ = int(1e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #     debugFilter={*HlsDebugBundle.ALL_RELIABLE,
    #                   HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    #                   HlsDebugBundle.DBG_4_0_addSignalNamesToData,
    #                   HlsDebugBundle.DBG_5_0_hwtHlsStats,
    #                   # HlsDebugBundle.DBG_4_4_syncLoweringAbc,
    #                   # HlsDebugBundle.DBG_4_4_syncLoweringNodes,
    #                   },
    #     llvmCliArgs=[
    #          # LLVM_CLI_COMMON_OPTS.STATS_JSON,
    #          # LLVM_CLI_COMMON_OPTS.TIME_TRACE,
    #          # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
    #          # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
    #          # LLVM_CLI_COMMON_OPTS.TIME_PASSES,
    #         ]
    #     )))
    import unittest
    import sys
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(ChannelThreadCommunicationTC)
    # suite = unittest.TestSuite([ChannelThreadCommunicationTC('test_SequentialShifterInOtherThread1')])
    runner = unittest.TextTestRunner(verbosity=3)
    sys.exit(not runner.run(suite).wasSuccessful())

