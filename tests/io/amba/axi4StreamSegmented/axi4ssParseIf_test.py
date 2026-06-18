#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
from hwtLib.amba.axi4SSegmentedSimFrameUtils import Axi4StreamSegmentedFrameUtils
from tests.io.amba.axi4Stream.axi4sParseIf_test import Axi4SParseIfTC
from tests.io.amba.axi4StreamSegmented.axi4ssParseIf import Axi4SSParse2If2B, \
    Axi4SSParse2If, Axi4SSParse2IfAndSequel


class Axi4SSParseIf_1Seg_TC(Axi4SParseIfTC):
    SEGMENT_CNT = 1
    _SimFrameUtils = Axi4StreamSegmentedFrameUtils
    __platformKwargs = dict(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
            # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER,
            # LLVM_CLI_COMMON_OPTS.debugOnly("block-freq"),
        ],
        # runTestAfterEachPass=True,
        # runTestAfterEachMirPass=True,
        # runTestAfterPassFilter=["hwtHls::StreamSegmentLoopUnrollPass", ]
    )

    def _test_Axi4SParse2If2B(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SSParse2If2B()
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.SEGMENT_CNT = self.SEGMENT_CNT
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If2B(dut, N, platformKwArgs=self.__platformKwargs)

    def _test_Axi4SParse2If(self, DATA_WIDTH:int, freq=int(1e6), N=16):
        dut = Axi4SSParse2If()
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.SEGMENT_CNT = self.SEGMENT_CNT
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2If(dut, N, platformKwArgs=self.__platformKwargs)

    def _test_Axi4SParse2IfAndSequel(self, DATA_WIDTH:int, freq=int(1e6), N=16, WRITE_FOOTER=True):
        dut = Axi4SSParse2IfAndSequel()
        dut.WRITE_FOOTER = WRITE_FOOTER
        dut.SEGMENT_DATA_WIDTH = DATA_WIDTH
        dut.SEGMENT_CNT = self.SEGMENT_CNT
        dut.CLK_FREQ = freq
        self._run_test_Axi4SParse2IfAndSequel(dut, N, WRITE_FOOTER, platformKwArgs=self.__platformKwargs)


class Axi4SSParseIf_2Seg_TC(Axi4SSParseIf_1Seg_TC):
    SEGMENT_CNT = 2


class Axi4SSParseIf_3Seg_TC(Axi4SSParseIf_1Seg_TC):
    SEGMENT_CNT = 3


class Axi4SSParseIf_4Seg_TC(Axi4SSParseIf_1Seg_TC):
    SEGMENT_CNT = 4


Axi4SSParseIf_TCs = [Axi4SSParseIf_1Seg_TC, Axi4SSParseIf_2Seg_TC, Axi4SSParseIf_3Seg_TC, Axi4SSParseIf_4Seg_TC]

if __name__ == '__main__':
    from hwtHls.platform.virtual import VirtualHlsPlatform

    from hwt.synth import to_rtl_str
    m = Axi4SSParse2IfAndSequel()
    m.WRITE_FOOTER = True
    m.SEGMENT_CNT = 2
    m.SEGMENT_DATA_WIDTH = 24
    m.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[
            LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
            # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
            # LLVM_CLI_COMMON_OPTS.DEBUG_PASS_MANAGER
        ]
    )
    # print(to_rtl_str(m, target_platform=p))

    testLoader = unittest.TestLoader()

    # HBits(30).from_py(50331652 & 0x170000ff)._reinterpret_cast(dut.i.WORD_T)

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([FixpDiv_TC('test_div_py')])
    suite = unittest.TestSuite([testLoader.loadTestsFromTestCase(tc) for tc in Axi4SSParseIf_TCs])
    # suite = testLoader.loadTestsFromTestCase(Axi4SSParseIf_2Seg_TC)
    # suite = unittest.TestSuite([Axi4SSParseIf_1Seg_TC("test_Axi4SParse2If_16b_100MHz")])
    suite = unittest.TestSuite([Axi4SSParseIf_1Seg_TC("test_Axi4SParse2IfAndSequel_16b_100MHz")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
