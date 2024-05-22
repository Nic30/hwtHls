#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
from typing import List
import unittest

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwt.hwModule import HwModule
from hwtHls.llvm.llvmIr import LlvmCompilationBundle, MachineFunction, Function
from hwtHls.platform.platform import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.ssa.analysis.llvmIrInterpret import LlvmIrInterpret, \
    SimIoUnderflowErr
from hwtHls.ssa.analysis.llvmMirInterpret import LlvmMirInterpret
from hwtLib.amba.axi4s import axi4s_send_bytes, packAxi4SFrame
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import  int_to_int_list, mask
from tests.io.amba.axi4Stream.axi4sParseIf import Axi4SParse2If2B, Axi4SParse2IfLess, Axi4SParse2If, Axi4SParse2IfAndSequel
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class Axi4SParseIfTC(SimTestCase):

    def _test_Axi4SParse2If2B(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SParse2If2B()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        T1 = HStruct(
            (HBits(8), "v0"),
        )
        T2 = HStruct(
            (HBits(8), "v0"),
            (HBits(8), "v1"),
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
            v = v._reinterpret_cast(HBits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.main, inputFrames, outputRef)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir))

        for f in inputFrames:
            axi4s_send_bytes(dut.i, f)

        t = int(freq_to_period(freq)) * (len(dut.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(dut.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dut.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _testLlvmIr(self, dut: HwModule, F: Function, inputFrames: List[List[int]], outputRef: List[int]):
        dataIn = []
        for refFrame in inputFrames:
            t = HBits(8)[len(refFrame)]
            _data_B = t.from_py(refFrame)
            axiWords = packAxi4SFrame(dut.DATA_WIDTH, _data_B, withStrb=False)
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
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _testLlvmMir(self, dut: HwModule, MF: MachineFunction, inputFrames: List[List[int]], outputRef: List[int]):
        dataIn = []
        for refFrame in inputFrames:
            t = HBits(8)[len(refFrame)]
            _data_B = t.from_py(refFrame)
            axiWords = packAxi4SFrame(dut.DATA_WIDTH, _data_B, withStrb=False)
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
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    # Axi4SParse2IfLess

    def _test_Axi4SParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SParse2If()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq

        T1 = HStruct(
            (HBits(16), "v0"),
            (HBits(8), "v1"),
        )
        T2 = HStruct(
            (HBits(16), "v0"),
            (HBits(16), "v1"),
        )
        T4 = HStruct(
            (HBits(16), "v0"),
            (HBits(32), "v1"),
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
            v = v._reinterpret_cast(HBits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            tc._testLlvmIr(dut, llvm.main, inputFrames, outputRef)

        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir))

        for f in inputFrames:
            axi4s_send_bytes(dut.i, f)

        t = int(freq_to_period(freq)) * (len(dut.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(dut.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dut.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _test_Axi4SParse2IfAndSequel(self, DATA_WIDTH:int, freq=int(1e6), N=16, WRITE_FOOTER=True, USE_PY_FRONTEND=False):
        dut = Axi4SParse2IfAndSequel()
        dut.WRITE_FOOTER = WRITE_FOOTER
        dut.DATA_WIDTH = DATA_WIDTH
        dut.USE_PY_FRONTEND = USE_PY_FRONTEND
        dut.CLK_FREQ = freq

        T0 = HStruct(
            (HBits(16), "v0"),
            (HBits(8), "v2"),
        )
        T2 = HStruct(
            (HBits(16), "v0"),
            (HBits(24), "v1"),
            (HBits(8), "v2"),
        )
        T4 = HStruct(
            (HBits(16), "v0"),
            (HBits(32), "v1"),
            (HBits(8), "v2"),
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
            v = v._reinterpret_cast(HBits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        tc = self

        def testLlvmOptIr(llvm: LlvmCompilationBundle):
            # try:
            tc._testLlvmIr(dut, llvm.main, inputFrames, outputRef)

            # except NotImplementedError:
            #    pass
        def testLlvmOptMir(llvm: LlvmCompilationBundle):
            tc._testLlvmMir(dut, llvm.getMachineFunction(llvm.main), inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
                debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                    HlsDebugBundle.DBG_20_addSignalNamesToSync}),
                optIrTest=testLlvmOptIr,
                optMirTest=testLlvmOptMir,
                # runTestAfterEachPass=True
        ))

        dut.i._ag.presetBeforeClk = True
        for f in inputFrames:
            axi4s_send_bytes(dut.i, f)

        t = int(freq_to_period(freq)) * (len(dut.i._ag.data) + 10) * 2
        if WRITE_FOOTER:
            t *= 2
        self.runSim(t)

        self.assertValSequenceEqual(dut.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dut.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    # Axi4SParse2If2B
    def test_Axi4SParse2If2B_8b_1MHz(self):
        self._test_Axi4SParse2If2B(8)

    def test_Axi4SParse2If2B_16b_1MHz(self):
        self._test_Axi4SParse2If2B(16)

    def test_Axi4SParse2If2B_24b_1MHz(self):
        self._test_Axi4SParse2If2B(24)

    def test_Axi4SParse2If2B_8b_40MHz(self):
        self._test_Axi4SParse2If2B(8, freq=int(40e6))

    def test_Axi4SParse2If2B_16b_40MHz(self):
        self._test_Axi4SParse2If2B(16, freq=int(40e6))

    def test_Axi4SParse2If2B_24b_40MHz(self):
        self._test_Axi4SParse2If2B(24, freq=int(40e6))

    def test_Axi4SParse2If2B_8b_100MHz(self):
        self._test_Axi4SParse2If2B(8, freq=int(100e6))

    def test_Axi4SParse2If2B_16b_100MHz(self):
        self._test_Axi4SParse2If2B(16, freq=int(100e6))

    def test_Axi4SParse2If2B_24b_100MHz(self):
        self._test_Axi4SParse2If2B(24, freq=int(100e6))

    # Axi4SParse2If
    def test_Axi4SParse2If_8b_1MHz(self):
        self._test_Axi4SParse2If(8)

    def test_Axi4SParse2If_16b_1MHz(self):
        self._test_Axi4SParse2If(16)

    def test_Axi4SParse2If_24b_1MHz(self):
        self._test_Axi4SParse2If(24)

    def test_Axi4SParse2If_48b_1MHz(self):
        self._test_Axi4SParse2If(48)

    def test_Axi4SParse2If_512b_1MHz(self):
        self._test_Axi4SParse2If(512)

    def test_Axi4SParse2If_8b_40MHz(self):
        self._test_Axi4SParse2If(8, freq=int(40e6))

    def test_Axi4SParse2If_16b_40MHz(self):
        self._test_Axi4SParse2If(16, freq=int(40e6))

    def test_Axi4SParse2If_24b_40MHz(self):
        self._test_Axi4SParse2If(24, freq=int(40e6))

    def test_Axi4SParse2If_48b_40MHz(self):
        self._test_Axi4SParse2If(48, freq=int(40e6))

    def test_Axi4SParse2If_512b_40MHz(self):
        self._test_Axi4SParse2If(512, freq=int(40e6))

    def test_Axi4SParse2If_8b_100MHz(self):
        self._test_Axi4SParse2If(8, freq=int(100e6))

    def test_Axi4SParse2If_16b_100MHz(self):
        self._test_Axi4SParse2If(16, freq=int(100e6))

    def test_Axi4SParse2If_24b_100MHz(self):
        self._test_Axi4SParse2If(24, freq=int(100e6))

    def test_Axi4SParse2If_48b_100MHz(self):
        self._test_Axi4SParse2If(48, freq=int(100e6))

    def test_Axi4SParse2If_512b_100MHz(self):
        self._test_Axi4SParse2If(512, freq=int(100e6))

    # Axi4SParse2IfAndSequel
    def test_Axi4SParse2IfAndSequel_8b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(8)

    def test_Axi4SParse2IfAndSequel_16b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(16)

    def test_Axi4SParse2IfAndSequel_24b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(24)

    def test_Axi4SParse2IfAndSequel_48b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, N=4)

    def test_Axi4SParse2IfAndSequel_512b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(512)

    def test_Axi4SParse2IfAndSequel_8b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_16b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_24b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_48b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_512b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_8b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(100e6))

    def test_Axi4SParse2IfAndSequel_16b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(100e6))

    def test_Axi4SParse2IfAndSequel_24b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(100e6))

    def test_Axi4SParse2IfAndSequel_48b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(100e6))

    def test_Axi4SParse2IfAndSequel_512b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(100e6))

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_8b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_16b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_24b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_48b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_512b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_8b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(40e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_16b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(40e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_24b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(40e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_48b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(40e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_512b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(40e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_8b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_16b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_24b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_48b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_512b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(100e6), WRITE_FOOTER=False)


if __name__ == '__main__':
    #from hwt.synth import to_rtl_str
    #m = Axi4SParse2IfAndSequel()
    #m.WRITE_FOOTER = True
    #m.DATA_WIDTH = 16
    #m.CLK_FREQ = int(1e6)
    #print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #    debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
    #        HlsDebugBundle.DBG_20_addSignalNamesToSync
    #}))))
    
    testLoader = unittest.TestLoader()
    
    # suite = unittest.TestSuite([Axi4SParseIfTC("test_Axi4SParse2If_24b_100MHz")])
    suite = testLoader.loadTestsFromTestCase(Axi4SParseIfTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
