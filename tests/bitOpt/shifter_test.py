#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, Set

from hwt.hdl.types.bits import HBits
from hwt.math import log2ceil
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.ast.astToSsa import HlsAstToSsa
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll
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

    def _test_shifter(self, dut: ShifterLeft0, timeMultiplier=1,
                      debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                      runTestAfterEachPass=False):
        MASK = mask(dut.DATA_WIDTH)
        TEST_DATA = [
            (MASK, i) for i in range(dut.DATA_WIDTH)
        ]
        REF_DATA = [MASK & (d << sh) for d, sh in TEST_DATA]

        dut.CLK_FREQ = int(1e6)
        wallTime = len(REF_DATA) * 1000
        dataTy = HBits(dut.DATA_WIDTH)
        shTy = HBits(log2ceil(dut.DATA_WIDTH))
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

            def runMirToHlsNetlist(self,
                              hls: "HlsScope", toSsa: HlsAstToSsa,
                              mf: MachineFunction, *args, **kwargs):
                self.runTestOnMachineFuncion(mf)
                return super(TestPlatform, self).runMirToHlsNetlist(hls, toSsa, mf,
                                                                       *args, **kwargs)

        self.compileSimAndStart(dut, target_platform=TestPlatform(debugFilter=debugFilter))  # debugFilter=HlsDebugBundle.ALL_RELIABLE
        for i, sh in TEST_DATA:
            dut.i._ag.data.append(i)
            dut.sh._ag.data.append(sh)

        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        dut.i._ag.presetBeforeClk = True
        dut.sh._ag.presetBeforeClk = True
        dut.o._ag.presetBeforeClk = True
        self.runSim((int(len(TEST_DATA) * timeMultiplier + 1)) * int(CLK_PERIOD))
        BaseIrMirRtl_TC._test_no_comb_loops(self)

        self.assertValSequenceEqual(dut.o._ag.data, REF_DATA)
        self.rtl_simulator_cls = None

    def test_ShifterLeft0(self):
        dut = ShifterLeft0()
        self._test_shifter(dut)

    def test_ShifterLeft1(self):
        dut = ShifterLeft1()
        self._test_shifter(dut)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_noUnroll(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.DATA_WIDTH = 3
        self._test_shifter(dut, timeMultiplier=8)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol2(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(dut, timeMultiplier=4, 
                           debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                               HlsDebugBundle.DBG_20_addSignalNamesToSync,
                               HlsDebugBundle.DBG_20_addSignalNamesToData})
        )

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrol4(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(dut, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithWhileNot0_unrolFull(self):
        dut = ShifterLeftUsingHwLoopWithWhileNot0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
        self._test_shifter(dut, runTestAfterEachPass=False)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_noUnroll(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        # dut.DATA_WIDTH = 3
        # dut.FN_META = PyBytecodeSkipPass(["hwtHls::SlicesToIndependentVariablesPass", ])
        # , debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync})
        self._test_shifter(dut, timeMultiplier=8)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 2)
        self._test_shifter(dut, timeMultiplier=4, debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync,
                                                     HlsDebugBundle.DBG_20_addSignalNamesToData}))

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrol4(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, 4)
        self._test_shifter(dut, timeMultiplier=2)

    def test_ShifterLeftUsingHwLoopWithBreakIf0_unrolFull(self):
        dut = ShifterLeftUsingHwLoopWithBreakIf0()
        dut.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
        self._test_shifter(dut, timeMultiplier=1.2)

    def test_ShifterLeftBarrelUsingLoop0(self):
        dut = ShifterLeftBarrelUsingLoop0()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingLoop1(self):
        dut = ShifterLeftBarrelUsingLoop1()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingLoop2(self):
        dut = ShifterLeftBarrelUsingLoop2()
        self._test_shifter(dut)

    def test_ShifterLeftBarrelUsingPyExprConstructor(self):
        dut = ShifterLeftBarrelUsingPyExprConstructor()
        self._test_shifter(dut)


if __name__ == "__main__":
    # from hwt.synth import to_rtl_str
    # dut = ShifterLeftUsingHwLoopWithWhileNot0()
    # # u.UNROLL_META = PyBytecodeLLVMLoopUnroll(True, dut.DATA_WIDTH - 1)
    # dut.CLK_FREQ = int(1e6)
    # print(to_rtl_str(dut, target_platform=VirtualHlsPlatform(
    #   debugFilter=HlsDebugBundle.ALL_RELIABLE.union({HlsDebugBundle.DBG_20_addSignalNamesToSync,
    #                                                  HlsDebugBundle.DBG_20_addSignalNamesToData}))))  # .union(HlsDebugBundle.DBG_FRONTEND)

    import unittest
    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([ShifterTC("test_ShifterLeftUsingHwLoopWithBreakIf0_unrol2")])
    suite = testLoader.loadTestsFromTestCase(ShifterTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
        
