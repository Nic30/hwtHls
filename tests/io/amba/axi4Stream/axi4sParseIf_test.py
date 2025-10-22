#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
from typing import List
import unittest

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtSimApi.utils import freq_to_period
from pyMathBitPrecise.bit_utils import  int_to_int_list, mask
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC
from tests.io.amba.axi4Stream._baseAxi4SPktInPktOutTC import BaseAxi4SPktInPktOutTC
from tests.io.amba.axi4Stream.axi4sParseIf import Axi4SParse2If2B, Axi4SParse2IfLess, Axi4SParse2If, Axi4SParse2IfAndSequel
from tests.testLlvmIrAndMirPlatform import TestLlvmIrAndMirPlatform


class Axi4SParseIfTC(SimTestCase):
    _Axi4StreamSimFrameUtils = Axi4StreamSimFrameUtils

    def _testLlvmIrOrMir(self, platform: TestLlvmIrAndMirPlatform, toLlvm: ToLlvmIrTranslator, isMir: bool, inputFrames: List[List[int]], outputRef: List[int]):
        dut = toLlvm.parentHwModule
        fu = self._Axi4StreamSimFrameUtils.from_HwIO(dut.i)
        dataIn = BaseAxi4SPktInPktOutTC._packFrames(fu, inputFrames)
        # for f in inputFrames:
        #     print(f)
        # for x in dataIn:
        #     print(x)
        dataOut = []
        args = [iter(dataIn), dataOut]
        BaseIrMirRtl_TC._runLlvmIrOrMir(self, platform, toLlvm, "", None, isMir, args)
        self.assertValSequenceEqual(dataOut, outputRef, "[%s] != [%s]" % (
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dataOut),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _test_Axi4SParse2If2B(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SParse2If2B()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If2B(dut, N)

    def _run_test_Axi4SParse2If2B(self, dut: Axi4SParse2If2B, N:int):
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

        def testLlvmOptIr(*args):
            tc._testLlvmIrOrMir(*args, False, inputFrames, outputRef)

        def testLlvmOptMir(*args):
            tc._testLlvmIrOrMir(*args, True, inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir))

        fu = self._Axi4StreamSimFrameUtils.from_HwIO(dut.i)
        for f in inputFrames:
            fu.send_bytes(f, dut.i._ag.data)

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(dut.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dut.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    # Axi4SParse2IfLess

    def _test_Axi4SParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SParse2If()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If(dut, N)

    def _run_test_Axi4SParse2If(self, dut: Axi4SParse2If, N:int):
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

        def testLlvmOptIr(*args):
            tc._testLlvmIrOrMir(*args, False, inputFrames, outputRef)

        def testLlvmOptMir(*args):
            tc._testLlvmIrOrMir(*args, True, inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
            optIrTest=testLlvmOptIr, optMirTest=testLlvmOptMir,
            llvmCliArgs=[
                LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            ]
            # runTestAfterEachPass=True,
            # runTestAfterEachIrPass=True,
            # runTestAfterEachMirPass=True

            ))

        fu = self._Axi4StreamSimFrameUtils.from_HwIO(dut.i)
        for f in inputFrames:
            fu.send_bytes(f, dut.i._ag.data)

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * 2
        self.runSim(t)

        self.assertValSequenceEqual(dut.o._ag.data, outputRef, "%r [%s] != [%s]" % (
            dut.o,
            ", ".join("0x%x" % int(i) if i._is_full_valid() else repr(i) for i in dut.o._ag.data),
            ", ".join("0x%x" % i for i in outputRef)
        ))

    def _test_Axi4SParse2IfAndSequel(self, DATA_WIDTH:int, freq=int(1e6), N=16, WRITE_FOOTER=True):
        dut = Axi4SParse2IfAndSequel()
        dut.WRITE_FOOTER = WRITE_FOOTER
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2IfAndSequel(dut, N, WRITE_FOOTER)

    def _run_test_Axi4SParse2IfAndSequel(self, dut: Axi4SParse2IfAndSequel, N:int, WRITE_FOOTER:bool):
        N = 2
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
        for _ in range(N):
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
                outputRef.append(v1)

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

        def testLlvmOptIr(*args):
            # try:
            tc._testLlvmIrOrMir(*args, False, inputFrames, outputRef)

            # except NotImplementedError:
            #    pass
        def testLlvmOptMir(*args):
            tc._testLlvmIrOrMir(*args, True, inputFrames, outputRef)

        self.compileSimAndStart(dut, target_platform=TestLlvmIrAndMirPlatform(
                # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                #    HlsDebugBundle.DBG_4_0_addSignalNamesToSync}),
                optIrTest=testLlvmOptIr,
                optMirTest=testLlvmOptMir,
                # runTestAfterEachPass=True,
                # runTestAfterEachIrPass=True,
                # runTestAfterEachMirPass=True,
                llvmCliArgs=[
                    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                ]
        ))

        dut.i._ag.presetBeforeClk = True
        fu = self._Axi4StreamSimFrameUtils.from_HwIO(dut.i)
        for f in inputFrames:
            fu.send_bytes(f, dut.i._ag.data)

        t = int(freq_to_period(dut.CLK_FREQ)) * (len(dut.i._ag.data) + 10) * 2
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
    # from hwtHls.platform.virtual import VirtualHlsPlatform
    # from hwt.synth import to_rtl_str
    # m = Axi4SParse2IfAndSequel()
    # m.WRITE_FOOTER = False
    # m.DATA_WIDTH = 16
    # m.CLK_FREQ = int(1e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #    debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
    #        HlsDebugBundle.DBG_4_0_addSignalNamesToSync
    # }))))

    testLoader = unittest.TestLoader()

    # suite = unittest.TestSuite([Axi4SParseIfTC("test_Axi4SParse2IfAndSequel_16b_100MHz")])
    suite = testLoader.loadTestsFromTestCase(Axi4SParseIfTC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
