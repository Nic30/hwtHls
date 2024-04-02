#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import inf
from typing import Optional, Set

from hwt.hdl.types.bits import Bits
from hwt.math import log2ceil
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeSkipPass
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, StringRef, Any, AnyToModule, \
    AnyToFunction, AnyToLoop, Module, Function, MachineFunction
from hwtHls.platform.debugBundle import DebugId
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtSimApi.triggers import StopSimumulation
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.bitOpt.shifter import ShifterLeft0, ShifterLeft1, \
    ShifterLeftBarrelUsingLoop0, ShifterLeftBarrelUsingLoop1, ShifterLeftBarrelUsingLoop2, \
    ShifterLeftBarrelUsingPyExprConstructor, ShifterLeftUsingHwLoopWithWhileNot0, \
    ShifterLeftUsingHwLoopWithBreakIf0


class ShifterTC(SimTestCase):

    def _test_shifter(self, u: ShifterLeft0, timeMultiplier=1,
                      debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                      runTestAfterEachPass=False):
        MASK = mask(u.DATA_WIDTH)
        TEST_DATA = [
            (MASK, i) for i in range(u.DATA_WIDTH)
        ]
        REF_DATA = [MASK & (d << sh) for d, sh in TEST_DATA]

        u.CLK_FREQ = int(1e6)
        wallTime = len(REF_DATA) * 1000
        dataTy = Bits(u.DATA_WIDTH)
        shTy = Bits(log2ceil(u.DATA_WIDTH))
        tc = self
        lastWorkingIr = None

        class TestPlatform(VirtualHlsPlatform):

            def runTestAfterPass(self, passName: StringRef, ir: Any):
                nonlocal lastWorkingIr
                F = AnyToFunction(ir)
                if F is None:
                    M = AnyToModule(ir)
                    if M is None:
                        L = AnyToLoop(ir)
                        assert L
                        F = L.getHeader().getParent()
                        assert F
                    else:
                        M: Module
                        for obj in M:
                            if isinstance(obj, Function):
                                F = obj
                                break
                        assert F is not None

                # print(passName.str())
                i = (dataTy.from_py(d) for d, _ in TEST_DATA)
                sh = (shTy.from_py(sh) for _, sh in TEST_DATA)
                o = []
                args = (iter(i), o, iter(sh))
                try:
                    interpret = LlvmIrInterpret(F)
                    interpret.run(args, wallTime=wallTime * interpret.timeStep)
                except SimIoUnderflowErr:
                    pass  # all inputs consumed
                except StopSimumulation:
                    pass

                o = [int(d) for d in o]
                # print("test:", [f"0x{int(d):x}" for d in o])
                tc.assertSequenceEqual(o, REF_DATA, f"Broken after {passName.str():s} lastWorking:\n{lastWorkingIr}\n broken:\n{str(F):s}")
                lastWorkingIr = str(F)

            def runTestOnMachineFuncion(self, MF: MachineFunction):
                i = (dataTy.from_py(d) for d, _ in TEST_DATA)
                sh = (shTy.from_py(sh) for _, sh in TEST_DATA)
                o = []
                args = (iter(i), o, iter(sh))
                try:
                    interpret = LlvmMirInterpret(MF)
                    interpret.run(args, wallTime=wallTime * interpret.timeStep)
                except SimIoUnderflowErr:
                    pass  # all inputs consumed
                except StopSimumulation:
                    pass
                o = [int(d) for d in o]
                # print("test:", [f"0x{int(d):x}" for d in o])
                tc.assertSequenceEqual(o, REF_DATA)

            def runSsaPasses(self, hls: "HlsScope", toSsa: HlsAstToSsa):
                super(TestPlatform, self).runSsaPasses(hls, toSsa)
                if runTestAfterEachPass:
                    toLlvm: ToLlvmIrTranslator = toSsa.start
                    llvm: LlvmCompilationBundle = toLlvm.llvm
                    llvm.registerAfterPassCallback(self.runTestAfterPass)

            def runNetlistTranslation(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa,
                              mf: MachineFunction, *args, **kwargs):
                self.runTestOnMachineFuncion(mf)
                return super(TestPlatform, self).runNetlistTranslation(hls, toSsa, mf,
                                                                       *args, **kwargs)

        self.compileSimAndStart(u, target_platform=TestPlatform(debugFilter=debugFilter))  # debugFilter=HlsDebugBundle.ALL_RELIABLE
        for i, sh in TEST_DATA:
            u.i._ag.data.append(i)
            u.sh._ag.data.append(sh)

        CLK_PERIOD = freq_to_period(u.clk.FREQ)
        u.i._ag.presetBeforeClk = True
        u.sh._ag.presetBeforeClk = True
        u.o._ag.presetBeforeClk = True
        self.runSim((int(len(TEST_DATA) * timeMultiplier + 1)) * int(CLK_PERIOD))
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        self.assertValSequenceEqual(u.o._ag.data, REF_DATA)
        self.rtl_simulator_cls = None

    def test_ShifterLeft0(self):
        u = ShifterLeft0()
        self._test_shifter(u)

    def test_ShifterLeft1(self):
        u = ShifterLeft1()
        self._test_shifter(u)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_noUnroll(self):
        u = ShifterLeftUsingHwLoopWithWhileNot0()
        u.DATA_WIDTH = 3
        self._test_shifter(u, timeMultiplier=8)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol2(self):
        u = ShifterLeftUsingHwLoopWithWhileNot0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(u, timeMultiplier=4, 
                           debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                               HlsDebugBundle.DBG_20_addSignalNamesToSync,
                               HlsDebugBundle.DBG_20_addSignalNamesToData})
        )

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol4(self):
        u = ShifterLeftUsingHwLoopWithWhileNot0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(u, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrolFull(self):
        u = ShifterLeftUsingHwLoopWithWhileNot0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, u.DATA_WIDTH - 1)
        self._test_shifter(u, runTestAfterEachPass=False)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_noUnroll(self):
        u = ShifterLeftUsingHwLoopWithBreakIf0()
        # u.DATA_WIDTH = 3
        # u.FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", ])
        # , debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync})
        self._test_shifter(u, timeMultiplier=8)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2(self):
        u = ShifterLeftUsingHwLoopWithBreakIf0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(u, timeMultiplier=4, debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync,
                                                     HlsDebugBundle.DBG_20_addSignalNamesToData}))

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol4(self):
        u = ShifterLeftUsingHwLoopWithBreakIf0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(u, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrolFull(self):
        u = ShifterLeftUsingHwLoopWithBreakIf0()
        u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, u.DATA_WIDTH - 1)
        self._test_shifter(u, timeMultiplier=1.2)

    def test_ShifterLeftBarrelUsingLoop0(self):
        u = ShifterLeftBarrelUsingLoop0()
        self._test_shifter(u)

    def test_ShifterLeftBarrelUsingLoop1(self):
        u = ShifterLeftBarrelUsingLoop1()
        self._test_shifter(u)

    def test_ShifterLeftBarrelUsingLoop2(self):
        u = ShifterLeftBarrelUsingLoop2()
        self._test_shifter(u)

    def test_ShifterLeftBarrelUsingPyExprConstructor(self):
        u = ShifterLeftBarrelUsingPyExprConstructor()
        self._test_shifter(u)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    # u = ShifterLeftUsingHwLoopWithBreakIf0()
    # u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, u.DATA_WIDTH - 1)
    # u.CLK_FREQ = int(1e6)
    # print(to_rtl_str(u, target_platform=VirtualHlsPlatform(
    #   debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync,
    #                                                  HlsDebugBundle.DBG_20_addSignalNamesToData}))))  # .union(HlsDebugBundle.DBG_FRONTEND)

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ShifterTC("test_ShifterLeftUsingHwLoopWithWhileNot0_unrol4")])
    suite = testLoader.loadTestsFromTestCase(ShifterTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
        
