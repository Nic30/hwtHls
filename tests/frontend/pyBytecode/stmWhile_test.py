#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from collections import deque
from pathlib import Path
from typing import Callable, Tuple, Union, Any, Optional, Iterable

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import MachineFunction, LLVMStringContext, Function
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.llvmIrInterpret import SimIoUnderflowErr, \
    LlvmIrInterpret
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.types.ctypes import uint8_t
from hwtSimApi.triggers import StopSimumulation
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter
from tests.baseSsaTest import BaseSsaTC
from tests.frontend.pyBytecode.stmWhile import HlsPythonHwWhile0, \
    HlsPythonHwWhile1, HlsPythonHwWhile2, HlsPythonHwWhile3, HlsPythonHwWhile4, \
    HlsPythonHwWhile5, HlsPythonHwWhile0b, HlsPythonHwWhile0c, \
    PragmaInline_HlsPythonHwWhile5, HlsPythonHwWhile6


class StmWhile_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonHwWhile0_ll(self):
        self._test_ll(HlsPythonHwWhile0)

    def test_HlsPythonHwWhile1_ll(self):
        self._test_ll(HlsPythonHwWhile1)

    def test_HlsPythonHwWhile2_ll(self):
        self._test_ll(HlsPythonHwWhile2)


LlvmSimFunctionArgT = Tuple[Union[list, deque]]


class ListRaisingStopSimumulationWhenFilled(list):

    def __init__(self, __iterable:Iterable, targetSize:int) -> None:
        list.__init__(self, __iterable)
        self.targetSize = targetSize

    def append(self, __object) -> None:
        list.append(self, __object)
        if len(self) >= self.targetSize:
            raise StopSimumulation()


class StmWhile_sim_TC(SimTestCase):

    def _testLlvmIr(self, strCtx: LLVMStringContext, F: Function, variantName:str, prepareArgs: Callable[LlvmSimFunctionArgT, []],
                    checkArgs:Callable[None, [LlvmSimFunctionArgT]], wallTime:Optional[int]):
        args = prepareArgs()
        try:
            with open(Path(self.DEFAULT_LOG_DIR, f"{self.getTestName()}{variantName:s}.llvmIrWave.vcd"), "w") as vcdFile:
                waveLog = VcdWriter(vcdFile)
                interpret = LlvmIrInterpret(F)
                interpret.installWaveLog(waveLog, strCtx)
                if wallTime is not None:
                    wallTime *= interpret.timeStep
                interpret.run(args, wallTime=wallTime)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        except StopSimumulation:
            pass
        checkArgs(args)

    def _testLlvmMir(self, strCtx: LLVMStringContext, MF: MachineFunction, prepareArgs: Callable[LlvmSimFunctionArgT, []],
                    checkArgs:Callable[None, [LlvmSimFunctionArgT]], wallTime:Optional[int]):
        args = prepareArgs()
        try:
            with open(Path(self.DEFAULT_LOG_DIR, f"{self.getTestName()}.llvmMirWave.vcd"), "w") as vcdFile:
                waveLog = VcdWriter(vcdFile)
                interpret = LlvmMirInterpret(MF)
                interpret.installWaveLog(waveLog, strCtx)
                if wallTime is not None:
                    wallTime *= interpret.timeStep
                interpret.run(args, wallTime=wallTime)
        except SimIoUnderflowErr:
            pass  # all inputs consumed
        except StopSimumulation:
            pass

        checkArgs(args)

    def _test(self, u: Unit, prepareArgs: Callable[LlvmSimFunctionArgT, []],
                    checkArgs:Callable[None, [LlvmSimFunctionArgT]],
                    prepareRtlSimArgs: Callable[Tuple[Any, int], [Unit]],  # returns tuple arg reference passes to checkRtlSimResults, simulation time
                    checkRtlSimResults: Callable[None, [Unit, Any]],
                    wallTimeIr: Optional[int]=None,
                    wallTimeOptIr: Optional[int]=None,
                    wallTimeOptMir: Optional[int]=None,
                    wallTimeRtlClks: Optional[int]=None,  # :attention: specified in clocks
                    freq=int(1e6)):
        """
        * Test non optimized LLVM IR
        * Test optimized LLVM IR
        * Test optimized LLVM MIR
        * Test RTL
        """
        u.CLK_FREQ = freq

        tc = self

        class TestVirtualHlsPlatform(VirtualHlsPlatform):

            def runSsaPasses(self, hls: HlsScope, toSsa: HlsAstToSsa):
                res = super(TestVirtualHlsPlatform, self).runSsaPasses(hls, toSsa)
                tr: ToLlvmIrTranslator = toSsa.start
                tc._testLlvmIr(tr.llvm.strCtx, tr.llvm.main, "", prepareArgs, checkArgs, wallTimeIr)
                return res

            def runNetlistTranslation(self,
                              hls: HlsScope, toSsa: HlsAstToSsa,
                              mf: MachineFunction, *args):
                tr: ToLlvmIrTranslator = toSsa.start
                tc._testLlvmIr(tr.llvm.strCtx, tr.llvm.main, ".opt", prepareArgs, checkArgs, wallTimeOptIr)
                tc._testLlvmMir(tr.llvm.strCtx, tr.llvm.getMachineFunction(tr.llvm.main), prepareArgs, checkArgs, wallTimeOptMir)
                netlist = super(TestVirtualHlsPlatform, self).runNetlistTranslation(hls, toSsa, mf, *args)
                return netlist

        self.compileSimAndStart(u, target_platform=TestVirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE))
        ref = prepareRtlSimArgs(u)
        t = int(wallTimeRtlClks * freq_to_period(freq))
        self.runSim(t)
        checkRtlSimResults(u, ref)

    def _testOneOut(self, u, model, OUT_CNT: int,
                   wallTimeIr: Optional[int]=None,
                   wallTimeOptIr: Optional[int]=None,
                   wallTimeOptMir: Optional[int]=None,
                   wallTimeRtlClks: Optional[int]=None):
        dataOutRef = []
        m = model(dataOutRef)
        try:
            for _ in range(OUT_CNT):
                next(m)
        except StopIteration:
            pass
        dataOutRef = [int(d) for d in dataOutRef]

        def prepareArgs():
            dataOut = ListRaisingStopSimumulationWhenFilled((), OUT_CNT)
            return (dataOut,)

        def checkArgs(args):
            dataOut = args[0]
            self.assertValSequenceEqual(dataOut, dataOutRef)

        def prepareRtlSimArgs(u):
            ref = dataOutRef
            return ref

        def checkRtlSimResults(u, ref):
            self.assertValSequenceEqual(u.o._ag.data, ref)

        self._test(u, prepareArgs, checkArgs, prepareRtlSimArgs, checkRtlSimResults,
                   wallTimeIr=wallTimeIr,
                   wallTimeOptIr=wallTimeOptIr,
                   wallTimeOptMir=wallTimeOptMir,
                   wallTimeRtlClks=wallTimeRtlClks)

    def _test_OneInOneOut(self, u, model, dataIn,
                          wallTimeIr: Optional[int]=None,
                          wallTimeOptIr: Optional[int]=None,
                          wallTimeOptMir: Optional[int]=None,
                          wallTimeRtlClks: Optional[int]=None):
        dataOutRef = []
        try:
            model(iter(dataIn), dataOutRef)
        except StopIteration:
            pass
        dataOutRef = [int(d) for d in dataOutRef]

        def prepareArgs():
            dataOut = []
            return (iter(dataIn), dataOut)

        def checkArgs(args):
            dataOut = args[1]
            self.assertValSequenceEqual(dataOut, dataOutRef)

        def prepareRtlSimArgs(u):
            u.i._ag.data.extend(dataIn)
            ref = dataOutRef
            return ref

        def checkRtlSimResults(u, ref):
            self.assertValSequenceEqual(u.o._ag.data, ref)

        if wallTimeRtlClks is None:
            wallTimeRtlClks = len(dataIn) + 1

        self._test(u, prepareArgs, checkArgs, prepareRtlSimArgs, checkRtlSimResults,
                   wallTimeIr=wallTimeIr,
                   wallTimeOptIr=wallTimeOptIr,
                   wallTimeOptMir=wallTimeOptMir,
                   wallTimeRtlClks=wallTimeRtlClks)

    def test_HlsPythonHwWhile0b(self):

        def model(dataOut):
            while True:
                dataOut.append(10)
                yield

        OUT_CNT = 8

        self._testOneOut(HlsPythonHwWhile0b(), model, OUT_CNT,
                         OUT_CNT * 10, OUT_CNT * 10,
                         OUT_CNT * 10, OUT_CNT + 1)

    def test_HlsPythonHwWhile0c(self):

        def model(dataIn, dataOut):
            while True:
                i = uint8_t.from_py(10)
                while True:
                    i += 1
                    dataOut.append(i)
                    if next(dataIn):
                        break

        OUT_CNT = 16
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(OUT_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile0c(), model, dataIn,
                   OUT_CNT * 20, OUT_CNT * 20,
                   OUT_CNT * 20, OUT_CNT + 2)

    # def test_HlsPythonHwWhile0(self):
    #    self._test(HlsPythonHwWhile0())
    #
    # def test_HlsPythonHwWhile1(self):
    #    self._test(HlsPythonHwWhile1())
    #
    def test_HlsPythonHwWhile2(self):

        def model(dataOut):
            i = uint8_t.from_py(0)
            while True:  # recognized as HW loop because of type
                if i <= 4:
                    dataOut.append(i)
                    yield
                elif i._eq(10):
                    break
                i += 1

            while True:
                dataOut.append(0)
                yield

        OUT_CNT = 16
        self._testOneOut(HlsPythonHwWhile2(), model, OUT_CNT,
                         OUT_CNT * 20, OUT_CNT * 20,
                         OUT_CNT * 20, OUT_CNT + 1)

    def test_HlsPythonHwWhile3(self):

        def model(dataIn, dataOut):
            while True:
                while True:
                    r1 = next(dataIn)
                    if r1 != 1:
                        r2 = next(dataIn)
                        dataOut.append(r2)
                        if r2 != 2:
                            break
                    else:
                        break

                dataOut.append(99)

        IN_CNT = 32
        in_t = Bits(8)
        dataIn = [in_t.from_py(self._rand.getrandbits(2)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(HlsPythonHwWhile3(), model, dataIn)

    def test_HlsPythonHwWhile4(self, uCls=HlsPythonHwWhile4):

        def model(dataIn, dataOut):
            while True:
                data = Bits(8).from_py(None)
                cntr = 8 - 1
                while cntr >= 0:
                    d = next(dataIn)
                    data = Concat(d, data[8:1])  # shift-in data from left
                    cntr = cntr - 1
                dataOut.append(data)

        IN_CNT = 32
        dataIn = [BIT.from_py(self._rand.getrandbits(1)) for _ in range(IN_CNT)]
        self._test_OneInOneOut(uCls(), model, dataIn)

    def test_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile5)

    def test_HlsPythonHwWhile6(self):
        self.test_HlsPythonHwWhile4(uCls=HlsPythonHwWhile6)

    def test_PragmaInline_HlsPythonHwWhile5(self):
        self.test_HlsPythonHwWhile4(uCls=PragmaInline_HlsPythonHwWhile5)


if __name__ == "__main__":
    import unittest

    testLoader = unittest.TestLoader()
    suite = unittest.TestSuite([StmWhile_sim_TC("test_HlsPythonHwWhile2")])
    # suite = testLoader.loadTestsFromTestCase(StmWhile_sim_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
