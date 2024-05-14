#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
from typing import List
import unittest

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwt.synthesizer.unit import Unit
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, MachineFunction, Function
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axis import axis_send_bytes, packAxiSFrame
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import  int_to_int_list, mask
from tests.io.amba.axiStream.axisParseIf import AxiSParse2If2B, AxiSParse2IfLess, AxiSParse2If, AxiSParse2IfAndSequel
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class AxiSParseIfTC(SimTestCase):

    def _test_AxiSParse2If2B(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        u = AxiSParse2If2B()
        u.DATA_WIDTH = DATA_WIDTH
        u.CLK_FREQ = freq
        T1 = HStruct(
            (Bits(8), "v0"),
        )
        T2 = HStruct(
            (Bits(8), "v0"),
            (Bits(8), "v1"),
        )

        inputFrames: List[List[int]] = []
        outputRef: List[int] = []
        for _ in range(N):
            T = self._rand.choice((T1, T2))
            if T is T1:
                d = {"v0": 1}
                outputRef.append(1)
            else:
                v1_t = T.field_by_name["v1"].dtype
                v1 = self._rand.getrandbits(v1_t.bit_length())
                d = {
                    "v0": 2,
                    "v1": v1
                }
                outputRef.append(v1)

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(Bits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(u, llvm.main, inputFrames, outputRef)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(u, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir))

        for f in inputFrames:
            axis_send_bytes(u.i, f)

        t = int(freq_to_period(freq)) * (len(u.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(u.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in u.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _testLlvmIr(self, u: Unit, F: Function, inputFrames: List[List[int]], outputRef: List[int]):
        dataIn = []
        for refFrame in inputFrames:
            t = Bits(8)[len(refFrame)]
            _data_B = t.from_py(refFrame)
            axiWords = packAxiSFrame(u.DATA_WIDTH, _data_B, withStrb=False)
            dataIn.extend(axiWords)

        dataIn = [Concat(BIT.from_py(d[1]), d[0]) for d in dataIn]
        dataOut = []
        args = [iter(dataIn), dataOut]
        interpret = LlvmIrInterpret(F)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass

        self.assertValSequenceEqual(dataOut, outputRef, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _testLlvmMir(self, u: Unit, MF: MachineFunction, inputFrames: List[List[int]], outputRef: List[int]):
        dataIn = []
        for refFrame in inputFrames:
            t = Bits(8)[len(refFrame)]
            _data_B = t.from_py(refFrame)
            axiWords = packAxiSFrame(u.DATA_WIDTH, _data_B, withStrb=False)
            dataIn.extend(axiWords)

        dataIn = [Concat(BIT.from_py(d[1]), d[0]) for d in dataIn]
        dataOut = []
        args = [iter(dataIn), dataOut]
        interpret = LlvmMirInterpret(MF)
        try:
            interpret.run(args)
        except SimIoUnderflowErr:
            pass

        self.assertValSequenceEqual(dataOut, outputRef, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    # AxiSParse2IfLess

    def _test_AxiSParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        u = AxiSParse2If()
        u.DATA_WIDTH = DATA_WIDTH
        u.CLK_FREQ = freq

        T1 = HStruct(
            (Bits(16), "v0"),
            (Bits(8), "v1"),
        )
        T2 = HStruct(
            (Bits(16), "v0"),
            (Bits(16), "v1"),
        )
        T4 = HStruct(
            (Bits(16), "v0"),
            (Bits(32), "v1"),
        )

        outputRef: List[int] = []
        inputFrames: List[List[int]] = []
        ALL_Ts = [T1, T2, T4]
        for _ in range(N):
            T = self._rand.choice(ALL_Ts)
            v1_t = T.field_by_name["v1"].dtype
            v1 = self._rand.getrandbits(v1_t.bit_length())
            d = {
                "v0": v1_t.bit_length() // 8,
                "v1": v1
            }
            if v1_t.bit_length() in (16, 32):
                outputRef.append(v1)

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(Bits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(u, llvm.main, inputFrames, outputRef)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(u, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir))

        for f in inputFrames:
            axis_send_bytes(u.i, f)

        t = int(freq_to_period(freq)) * (len(u.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(u.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in u.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _test_AxiSParse2IfAndSequel(self, DATA_WIDTH:int, freq=int(1e6), N=16, WRITE_FOOTER=True, USE_PY_FRONTEND=False):
        u = AxiSParse2IfAndSequel()
        u.WRITE_FOOTER = WRITE_FOOTER
        u.DATA_WIDTH = DATA_WIDTH
        u.USE_PY_FRONTEND = USE_PY_FRONTEND
        u.CLK_FREQ = freq

        T0 = HStruct(
            (Bits(16), "v0"),
            (Bits(8), "v2"),
        )
        T2 = HStruct(
            (Bits(16), "v0"),
            (Bits(24), "v1"),
            (Bits(8), "v2"),
        )
        T4 = HStruct(
            (Bits(16), "v0"),
            (Bits(32), "v1"),
            (Bits(8), "v2"),
        )

        outputRef: List[int] = []
        inputFrames: List[List[int]] = []
        ALL_Ts = [T0, T2, T4]
        for dbgI in range(N):
            dbgSkip = False
            T = self._rand.choice(ALL_Ts)
            v2 = self._rand.getrandbits(8)
            d = {
                "v0": {T0: 10, T2: 3, T4: 4}[T],
                "v2": v2
            }
            if T is not T0:  # (because T0 does not have v1)_
                v1_width = T.field_by_name["v1"].dtype.bit_length()
                v1 = self._rand.getrandbits(v1_width)
                d["v1"] = v1
                if not dbgSkip:
                    outputRef.append(v1)
            if dbgSkip:
                continue

            if WRITE_FOOTER:
                outputRef.append(v2)

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(Bits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            # try:
            tc._testLlvmIr(u, llvm.main, inputFrames, outputRef)

            # except NotImplementedError:
            #    pass
        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(u, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(u, target_platform=TestLlvmIrAndMirPlatform(
                debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                    HlsDebugBundle.DBG_20_addSignalNamesToSync}),
                optIrTest=testLlvmOptIr,
                optMirTest=testLlvmOptMir,
                # runTestAfterEachPass=True
        ))

        u.i._ag.presetBeforeClk = True
        for f in inputFrames:
            axis_send_bytes(u.i, f)

        t = int(freq_to_period(freq)) * (len(u.i._ag.data) + 10) * 2
        if WRITE_FOOTER:
            t *= 2
        self.runSim(t)

        self.assertValSequenceEqual(u.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            u.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in u.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    # AxiSParse2If2B
    def test_AxiSParse2If2B_8b_1MHz(self):
        self._test_AxiSParse2If2B(8)

    def test_AxiSParse2If2B_16b_1MHz(self):
        self._test_AxiSParse2If2B(16)

    def test_AxiSParse2If2B_24b_1MHz(self):
        self._test_AxiSParse2If2B(24)

    def test_AxiSParse2If2B_8b_40MHz(self):
        self._test_AxiSParse2If2B(8, freq=int(40e6))

    def test_AxiSParse2If2B_16b_40MHz(self):
        self._test_AxiSParse2If2B(16, freq=int(40e6))

    def test_AxiSParse2If2B_24b_40MHz(self):
        self._test_AxiSParse2If2B(24, freq=int(40e6))

    def test_AxiSParse2If2B_8b_100MHz(self):
        self._test_AxiSParse2If2B(8, freq=int(100e6))

    def test_AxiSParse2If2B_16b_100MHz(self):
        self._test_AxiSParse2If2B(16, freq=int(100e6))

    def test_AxiSParse2If2B_24b_100MHz(self):
        self._test_AxiSParse2If2B(24, freq=int(100e6))

    # AxiSParse2If
    def test_AxiSParse2If_8b_1MHz(self):
        self._test_AxiSParse2If(8)

    def test_AxiSParse2If_16b_1MHz(self):
        self._test_AxiSParse2If(16)

    def test_AxiSParse2If_24b_1MHz(self):
        self._test_AxiSParse2If(24)

    def test_AxiSParse2If_48b_1MHz(self):
        self._test_AxiSParse2If(48)

    def test_AxiSParse2If_512b_1MHz(self):
        self._test_AxiSParse2If(512)

    def test_AxiSParse2If_8b_40MHz(self):
        self._test_AxiSParse2If(8, freq=int(40e6))

    def test_AxiSParse2If_16b_40MHz(self):
        self._test_AxiSParse2If(16, freq=int(40e6))

    def test_AxiSParse2If_24b_40MHz(self):
        self._test_AxiSParse2If(24, freq=int(40e6))

    def test_AxiSParse2If_48b_40MHz(self):
        self._test_AxiSParse2If(48, freq=int(40e6))

    def test_AxiSParse2If_512b_40MHz(self):
        self._test_AxiSParse2If(512, freq=int(40e6))

    def test_AxiSParse2If_8b_100MHz(self):
        self._test_AxiSParse2If(8, freq=int(100e6))

    def test_AxiSParse2If_16b_100MHz(self):
        self._test_AxiSParse2If(16, freq=int(100e6))

    def test_AxiSParse2If_24b_100MHz(self):
        self._test_AxiSParse2If(24, freq=int(100e6))

    def test_AxiSParse2If_48b_100MHz(self):
        self._test_AxiSParse2If(48, freq=int(100e6))

    def test_AxiSParse2If_512b_100MHz(self):
        self._test_AxiSParse2If(512, freq=int(100e6))

    # AxiSParse2IfAndSequel
    def test_AxiSParse2IfAndSequel_8b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(8)

    def test_AxiSParse2IfAndSequel_16b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(16)

    def test_AxiSParse2IfAndSequel_24b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(24)

    def test_AxiSParse2IfAndSequel_48b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(48, N=4)

    def test_AxiSParse2IfAndSequel_512b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(512)

    def test_AxiSParse2IfAndSequel_8b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(8, freq=int(40e6))

    def test_AxiSParse2IfAndSequel_16b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(16, freq=int(40e6))

    def test_AxiSParse2IfAndSequel_24b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(24, freq=int(40e6))

    def test_AxiSParse2IfAndSequel_48b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(48, freq=int(40e6))

    def test_AxiSParse2IfAndSequel_512b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(512, freq=int(40e6))

    def test_AxiSParse2IfAndSequel_8b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(8, freq=int(100e6))

    def test_AxiSParse2IfAndSequel_16b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(16, freq=int(100e6))

    def test_AxiSParse2IfAndSequel_24b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(24, freq=int(100e6))

    def test_AxiSParse2IfAndSequel_48b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(48, freq=int(100e6))

    def test_AxiSParse2IfAndSequel_512b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(512, freq=int(100e6))

    def test_AxiSParse2IfAndSequel_NO_FOOTER_8b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(8, WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_16b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(16, WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_24b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(24, WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_48b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(48, WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_512b_1MHz(self):
        self._test_AxiSParse2IfAndSequel(512, WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_8b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(8, freq=int(40e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_16b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(16, freq=int(40e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_24b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(24, freq=int(40e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_48b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(48, freq=int(40e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_512b_40MHz(self):
        self._test_AxiSParse2IfAndSequel(512, freq=int(40e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_8b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(8, freq=int(100e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_16b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(16, freq=int(100e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_24b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(24, freq=int(100e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_48b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(48, freq=int(100e6), WRITE_FOOTER=False)

    def test_AxiSParse2IfAndSequel_NO_FOOTER_512b_100MHz(self):
        self._test_AxiSParse2IfAndSequel(512, freq=int(100e6), WRITE_FOOTER=False)


if __name__ == '__main__':
    #from hwt.synthesizer.utils import to_rtl_str
    #u = AxiSParse2IfAndSequel()
    #u.WRITE_FOOTER = True
    #u.DATA_WIDTH = 16
    #u.CLK_FREQ = int(1e6)
    #print(to_rtl_str(u, target_platform=VirtualHlsPlatform(
    #    debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
    #        HlsDebugBundle.DBG_20_addSignalNamesToSync
    #}))))
    
    testLoader = unittest.TestLoader()
    
    suite = unittest.TestSuite([AxiSParseIfTC("test_AxiSParse2If_24b_100MHz")])
    #suite = testLoader.loadTestsFromTestCase(AxiSParseIfTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
