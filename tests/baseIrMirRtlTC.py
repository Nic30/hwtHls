from collections import deque
from pathlib import Path
from typing import Iterable, Tuple, Union, Callable, Optional, Any, Set, \
    Generator, List

from hwt.hdl.const import HConst
from hwt.hwModule import HwModule
from hwt.serializer.combLoopAnalyzer import CombLoopAnalyzer
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.llvm.llvmIr import Function, LLVMStringContext, MachineFunction
from hwtHls.platform.platform import DebugId, HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.examples.errors.combLoops import freeze_set_of_sets
from hwtSimApi.triggers import StopSimumulation
from hwtSimApi.utils import freq_to_period
from pyDigitalWaveTools.vcd.writer import VcdWriter


LlvmSimFunctionArgT = Tuple[Union[list, deque]]


class ListRaisingStopSimumulationWhenFilled(list):

    def __init__(self, __iterable:Iterable, targetSize:int) -> None:
        list.__init__(self, __iterable)
        self.targetSize = targetSize

    def append(self, __object) -> None:
        list.append(self, __object)
        if len(self) >= self.targetSize:
            raise StopSimumulation()

    def extend(self, __iterable:Iterable) -> None:
        raise NotImplementedError()


class BaseIrMirRtl_TC(SimTestCase):
    """
    This class contains utility methods for testing simple circuit at LLVM IR, MIR and RTL level.
    """

    def _test_no_comb_loops(self):
        s = CombLoopAnalyzer()
        s.visit_HwModule(self.dut)
        comb_loops = freeze_set_of_sets(s.report())
        msg_buff = []
        for loop in comb_loops:
            msg_buff.append(10 * "-")
            for s in loop:
                msg_buff.append(str(s.resolve()[1:]))

        self.assertEqual(comb_loops, frozenset(), msg="\n".join(msg_buff))

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

    def _test(self, dut: HwModule,
              prepareIrAndMirArgs: Callable[LlvmSimFunctionArgT, []],
              checkIrAndMirArgs: Callable[None, [LlvmSimFunctionArgT]],
              prepareRtlSimArgs: Callable[Tuple[Any, int], [HwModule]],  # returns tuple arg reference passes to checkRtlSimResults, simulation time
              checkRtlSimResults: Callable[None, [HwModule, Any]],
              wallTimeIr: Optional[int]=None,
              wallTimeOptIr: Optional[int]=None,
              wallTimeOptMir: Optional[int]=None,
              wallTimeRtlClks: Optional[int]=None,  # :attention: specified in clocks
              freq=int(1e6),
              debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        """
        * Test non optimized LLVM IR
        * Test optimized LLVM IR
        * Test optimized LLVM MIR
        * Test RTL
        
        :param dut: a module which is translated and verified
        :param prepareIrAndMirArgs: a function which generates argument tuple for LLVM IR and MIR simulations
        :param checkIrAndMirArgs: a function which checks argument tuple outputs for correctness after LLVM IR and MIR simulations
        :param prepareRtlSimArgs: a function which add input data to input simulation agents (drivers) and returns
            values of outputs for later check in checkRtlSimResults
        :param checkRtlSimResults: A function which check the data in simulation agents (monitors) for correctness
        
        :param wallTimeIr: max number of clock cycles for no-opt LLVM IR simulation (1 instr = 1 clk)
        :param wallTimeOptIr: max number of clock cycles for opt LLVM IR simulation (1 instr = 1 clk)
        :param wallTimeOptMir: max number of clock cycles for opt LLVM MIR simulation (1 instr = 1 clk)
        :param wallTimeRtlClks: max number of clock cycles for RTL simulation (1 clk = period of time specified by dut clock frequency)
        :param freq: override of dut.CLK_FREQ
        :param debugFilter: An argument for HlsPlatform which can be used to trigger various debug outputs and transformations
        """
        dut.CLK_FREQ = freq

        tc = self

        class TestVirtualHlsPlatform(VirtualHlsPlatform):

            def runSsaPasses(self, hls: HlsScope, toSsa: HlsAstToSsa):
                res = super(TestVirtualHlsPlatform, self).runSsaPasses(hls, toSsa)
                tr: ToLlvmIrTranslator = toSsa.start
                tc._testLlvmIr(tr.llvm.strCtx, tr.llvm.main, "", prepareIrAndMirArgs, checkIrAndMirArgs, wallTimeIr)
                return res

            def runNetlistTranslation(self,
                              hls: HlsScope, toSsa: HlsAstToSsa,
                              mf: MachineFunction, *args):
                tr: ToLlvmIrTranslator = toSsa.start
                tc._testLlvmIr(tr.llvm.strCtx, tr.llvm.main, ".opt", prepareIrAndMirArgs, checkIrAndMirArgs, wallTimeOptIr)
                tc._testLlvmMir(tr.llvm.strCtx, tr.llvm.getMachineFunction(tr.llvm.main), prepareIrAndMirArgs, checkIrAndMirArgs, wallTimeOptMir)
                netlist = super(TestVirtualHlsPlatform, self).runNetlistTranslation(hls, toSsa, mf, *args)
                return netlist

        self.compileSimAndStart(dut, target_platform=TestVirtualHlsPlatform(debugFilter=debugFilter))
        self._test_no_comb_loops()
        ref = prepareRtlSimArgs(dut)
        t = int(wallTimeRtlClks * freq_to_period(freq))
        self.runSim(t)
        checkRtlSimResults(dut, ref)

    def _testOneOut(self, dut: HwModule,
                    model, OUT_CNT: int,
                    wallTimeIr: Optional[int]=None,
                    wallTimeOptIr: Optional[int]=None,
                    wallTimeOptMir: Optional[int]=None,
                    wallTimeRtlClks: Optional[int]=None,
                    freq=int(1e6),
                    debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        """
        :param model: a generator function which will be used as a model during verification
            on every compilation step
        
        For meaning of other params check :meth:`~._test`
        """
        dataOutRef = []
        m = model(dataOutRef)
        try:
            for _ in range(OUT_CNT):
                next(m)
        except StopIteration:
            pass
        dataOutRef = [int(d) for d in dataOutRef]

        def prepareIrAndMirArgs():
            dataOut = ListRaisingStopSimumulationWhenFilled((), OUT_CNT)
            return (dataOut,)

        def checkIrAndMirArgs(args):
            dataOut = args[0]
            self.assertValSequenceEqual(dataOut, dataOutRef)

        def prepareRtlSimArgs(u):
            ref = dataOutRef
            return ref

        def checkRtlSimResults(dut: HwModule, ref):
            self.assertValSequenceEqual(dut.o._ag.data, ref)

        self._test(dut, prepareIrAndMirArgs, checkIrAndMirArgs, prepareRtlSimArgs, checkRtlSimResults,
                   wallTimeIr=wallTimeIr,
                   wallTimeOptIr=wallTimeOptIr,
                   wallTimeOptMir=wallTimeOptMir,
                   wallTimeRtlClks=wallTimeRtlClks,
                   freq=freq,
                   debugFilter=debugFilter,
                   )

    def _test_OneInOneOut(self, dut: HwModule,
                          model,
                          dataIn,
                          wallTimeIr: Optional[int]=None,
                          wallTimeOptIr: Optional[int]=None,
                          wallTimeOptMir: Optional[int]=None,
                          wallTimeRtlClks: Optional[int]=None,
                          debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                          freq=int(1e6),
                          prepareIrAndMirArgs:Callable[[], Tuple[Generator[HConst, None, None], List[HConst]]]=None):
        """
        :param model: a function which process all inputs and generate all outputs
        For meaning of params check :meth:`~._testOneOut`
        """
        dataOutRef = []
        try:
            model(iter(dataIn), dataOutRef)
        except StopIteration:
            pass
        dataOutRef = [int(d) for d in dataOutRef]
        
        if prepareIrAndMirArgs is None:

            def prepareIrAndMirArgs():
                dataOut = []
                return (iter(dataIn), dataOut)

        def checkIrAndMirArgs(args):
            dataOut = args[1]
            self.assertValSequenceEqual(dataOut, dataOutRef)

        def prepareRtlSimArgs(dut):
            dut.i._ag.data.extend(dataIn)
            ref = dataOutRef
            return ref

        def checkRtlSimResults(dut, ref):
            self.assertValSequenceEqual(dut.o._ag.data, ref)

        if wallTimeRtlClks is None:
            wallTimeRtlClks = len(dataIn) + 1

        self._test(dut,
            prepareIrAndMirArgs, checkIrAndMirArgs,
            prepareRtlSimArgs, checkRtlSimResults,
            wallTimeIr=wallTimeIr,
            wallTimeOptIr=wallTimeOptIr,
            wallTimeOptMir=wallTimeOptMir,
            wallTimeRtlClks=wallTimeRtlClks,
            freq=freq,
            debugFilter=debugFilter,
        )
