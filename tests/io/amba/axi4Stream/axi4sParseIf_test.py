#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil
from typing import Optional
import unittest

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.struct import HStruct
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS, HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtLib.amba.axi4sSimFrameUtils import Axi4StreamSimFrameUtils
from hwtSimApi.agents.base import NOP
from pyMathBitPrecise.bit_utils import int_to_int_list, mask
from tests.io.amba.axi4Stream.axi4sParseIf import Axi4SParse2If2B, Axi4SParse2IfLess, Axi4SParse2If, Axi4SParse2IfAndSequel
from tests.passTestInjectorForDInDOutHwModule import PassTestInjectorForDInDOutHwModule
from tests.passTestIo import PassTestIoOut, errMsgFrormatter_HBitsAsHex
from tests.passTestIoStream import PassTestIoInStream


class Axi4SParseIfTC(SimTestCase):
    _SimFrameUtils = Axi4StreamSimFrameUtils
    _platformKwArgs = dict(
        # debugFilter={  
        #  *HlsDebugBundle.ALL_RELIABLE,
        # # HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
        # # HlsDebugBundle.DBG_4_0_addSignalNamesToData,
        # },
        llvmCliArgs=[
        #     LLVM_CLI_COMMON_OPTS.OVERWIRTE_BB_NAMES,
        #     LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
        #     LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
        #     LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL,
            LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        #    LLVM_CLI_COMMON_OPTS.VREGIFCVT_TRACE,
        ],
    )

    def _runTest(self, dut, inputFrames: list[int], outputRef: list[int],
                 platform:Optional[VirtualHlsPlatform]=None,
                 platformKwArgs=None,
                 wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,
                 ):
        if platformKwArgs is None:
            platformKwArgs = self._platformKwArgs
        passTests = PassTestInjectorForDInDOutHwModule(dut, self)
        passTests.bindData((PassTestIoInStream(self._SimFrameUtils, inputFrames, name="i"),
                            PassTestIoOut(outputRef, name="o", errMsgFormatter=errMsgFrormatter_HBitsAsHex)))
        # passTests.dbgOpenDiffOnIrErr = True
        passTests.setRunTestsAfter(
            # runTestAfterPassFilter=["hwtHls::SlicesMergePass"],
            #runTestAfterPassFilter=["hwtHls::StreamSegmentLoopUnrollPass"],
            runTestBeforeLlvmIrPasses=True,
            # runTestAfterEachPass=False,
            runTestAfterIrPasses=True,
            #runTestAfterEachIrPass=True,
            #runTestAfterIrInstrCombineChange=True,
            #runTestAfterIrCfgSimplify=True,
            runTestAfterMirPasses=True,
            # runTestAfterMirVRegIfConverterChange=False,
            # runTestAfterMirGISelCombinerChange=False,
            # runTestAfterEachHlsNetlistPass=False,
            runTestAfterHlsNetlistPasses=False)
        passTests.setTimeLimits(wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

        passTests.test_allInOne(platform=platform, platformKwArgs=platformKwArgs)

    def _test_Axi4SParse2If2B(self, DATA_WIDTH:int, freq=int(1e6), N=16,
                              wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,):
        dut = Axi4SParse2If2B()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If2B(dut, N, wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

    def _run_test_Axi4SParse2If2B(self, dut: Axi4SParse2If2B, N:int, platformKwArgs={},
                                  wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,):
        T1 = HStruct(
            (HBits(8), "v0"),
        )
        T2 = HStruct(
            (HBits(8), "v0"),
            (HBits(8), "v1"),
        )

        inputFrames: list[list[int]] = []
        outputRef: list[int] = []
        for _ in range(N):
            T = self._rand.choice((T1, T2, NOP))
            if T is T1:
                d = {"v0": 1}
                outputRef.append(1)
            elif T is T2:
                v1_t = T.field_by_name["v1"].dtype
                v1 = self._rand.getrandbits(v1_t.bit_length())
                d = {
                    "v0": 2,
                    "v1": v1
                }
                outputRef.append(v1)
            else:
                inputFrames.append(NOP)
                continue

            v = T.from_py(d)
            w = v._dtype.bit_length()
            v = v._reinterpret_cast(HBits(w))
            v.vld_mask = mask(w)
            v = int(v)
            data = int_to_int_list(v, 8, ceil(T.bit_length() / 8))
            inputFrames.append(data)

        self._runTest(dut, inputFrames, outputRef, platformKwArgs=platformKwArgs,
                      wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

    # Axi4SParse2IfLess

    def _test_Axi4SParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16,
                            wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,):
        dut = Axi4SParse2If()
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If(dut, N, wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

    def _run_test_Axi4SParse2If(self, dut: Axi4SParse2If, N:int,
                                platformKwArgs=None,
                                wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,):
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

        outputRef: list[int] = []
        inputFrames: list[list[int]] = []
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

        self._runTest(dut, inputFrames, outputRef, platformKwArgs=platformKwArgs,
                      wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

    def _test_Axi4SParse2IfAndSequel(self, DATA_WIDTH:int, freq=int(1e6), N=2, WRITE_FOOTER=True,
                 wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,):
        dut = Axi4SParse2IfAndSequel()
        dut.WRITE_FOOTER = WRITE_FOOTER
        dut.DATA_WIDTH = DATA_WIDTH
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2IfAndSequel(dut, N, WRITE_FOOTER,
                                              wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

    def _run_test_Axi4SParse2IfAndSequel(self, dut: Axi4SParse2IfAndSequel, N:int, WRITE_FOOTER:bool,
            platformKwArgs=dict(
                # debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
                #    # HlsDebugBundle.DBG_4_0_hwscheduleTrace,
                #    HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
                #    HlsDebugBundle.DBG_4_0_addSignalNamesToData,
                # }),
                llvmCliArgs=[
                    # LLVM_CLI_COMMON_OPTS.OVERWIRTE_BB_NAMES,
                    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                    # LLVM_CLI_COMMON_OPTS.VREGIFCVT_TRACE,
                    LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                    # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
                ]
            ),
            wallTimeRtlDefaultMultiplier:Optional[int]=NOT_SPECIFIED,
            ):
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

        outputRef: list[int] = []
        inputFrames: list[list[int]] = []
        ALL_Ts = [
            T0,
            T2,
            T4
                  ]
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

        self._runTest(dut, inputFrames, outputRef, platformKwArgs=platformKwArgs,
                      wallTimeRtlDefaultMultiplier=wallTimeRtlDefaultMultiplier)

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
        self._test_Axi4SParse2If(8, freq=int(40e6), wallTimeRtlDefaultMultiplier=2)

    def test_Axi4SParse2If_16b_40MHz(self):
        self._test_Axi4SParse2If(16, freq=int(40e6))

    def test_Axi4SParse2If_24b_40MHz(self):
        self._test_Axi4SParse2If(24, freq=int(40e6))

    def test_Axi4SParse2If_48b_40MHz(self):
        self._test_Axi4SParse2If(48, freq=int(40e6))

    def test_Axi4SParse2If_512b_40MHz(self):
        self._test_Axi4SParse2If(512, freq=int(40e6))

    def test_Axi4SParse2If_8b_100MHz(self):
        self._test_Axi4SParse2If(8, freq=int(100e6), wallTimeRtlDefaultMultiplier=8)

    def test_Axi4SParse2If_16b_100MHz(self):
        self._test_Axi4SParse2If(16, freq=int(100e6), wallTimeRtlDefaultMultiplier=2)

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
        self._test_Axi4SParse2IfAndSequel(16, wallTimeRtlDefaultMultiplier=3)

    def test_Axi4SParse2IfAndSequel_24b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, wallTimeRtlDefaultMultiplier=2)

    def test_Axi4SParse2IfAndSequel_48b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, wallTimeRtlDefaultMultiplier=1.5)

    def test_Axi4SParse2IfAndSequel_512b_1MHz(self):
        self._test_Axi4SParse2IfAndSequel(512)

    def test_Axi4SParse2IfAndSequel_8b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_16b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(40e6), wallTimeRtlDefaultMultiplier=3)

    def test_Axi4SParse2IfAndSequel_24b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(40e6), wallTimeRtlDefaultMultiplier=2)

    def test_Axi4SParse2IfAndSequel_48b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_512b_40MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(40e6))

    def test_Axi4SParse2IfAndSequel_8b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(8, freq=int(100e6), wallTimeRtlDefaultMultiplier=3)

    def test_Axi4SParse2IfAndSequel_16b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(100e6), wallTimeRtlDefaultMultiplier=5.5)

    def test_Axi4SParse2IfAndSequel_24b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(100e6), wallTimeRtlDefaultMultiplier=4)

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
        self._test_Axi4SParse2IfAndSequel(8, freq=int(100e6), WRITE_FOOTER=False, wallTimeRtlDefaultMultiplier=2)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_16b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(16, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_24b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(24, freq=int(100e6), WRITE_FOOTER=False, wallTimeRtlDefaultMultiplier=3)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_48b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(48, freq=int(100e6), WRITE_FOOTER=False)

    def test_Axi4SParse2IfAndSequel_NO_FOOTER_512b_100MHz(self):
        self._test_Axi4SParse2IfAndSequel(512, freq=int(100e6), WRITE_FOOTER=False)


if __name__ == '__main__':
    from hwt.synth import to_rtl_str
    # m = Axi4SParse2IfAndSequel()
    # # m = Axi4SParse2If2B()
    # m.WRITE_FOOTER = True
    # m.DATA_WIDTH = 16
    # m.CLK_FREQ = int(1e6)
    # print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
    #    llvmCliArgs=[
    #         LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
    #         LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
    #         LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
    #    ],
    #    debugFilter=HlsDebugBundle.ALL_RELIABLE.union({
    #        HlsDebugBundle.DBG_4_0_addSignalNamesToSync,
    #        HlsDebugBundle.DBG_4_0_addSignalNamesToData,
    # }))))

    testLoader = unittest.TestLoader()

    suite = testLoader.loadTestsFromTestCase(Axi4SParseIfTC)
    # suite = unittest.TestSuite([Axi4SParseIfTC("test_Axi4SParse2If_8b_100MHz")])
    # suite = unittest.TestSuite([Axi4SParseIfTC("test_Axi4SParse2IfAndSequel_24b_1MHz")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
