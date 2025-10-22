#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from binascii import crc32

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaLoop import PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc, \
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.platform.debugBundle import HlsDebugBundle
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.logic.crcPoly import CRC_32, CRC_POLY
from pyMathBitPrecise.bit_utils import mask
from tests.crypto.crcFinalize import CrcFinalizeHardblock
from tests.crypto.crcStep import CrcStepHardblock
from tests.io.amba.axi4Stream._baseAxi4SPktInPktOutTC import BaseAxi4SPktInScalarOutTC


class Axi4SCrc32(HwModule):
    """
    Compute CRC-32 of a frame
    """

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))
        self.POLY: CRC_POLY = HwParam(CRC_32)
        self.CRC_MAX_BYTES_PROCESSED_IN_PARALLEL = HwParam(None)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = True
            self.tx: HwIODataRdVld = HwIODataRdVld()._m()  # :note: name tx is picked for compatiblity with existing test utilities
            self.tx.DATA_WIDTH = self.POLY.WIDTH

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream):
        POLY = self.POLY
        b8_t = HBits(8)
        # in preproc because variables storing functions must be preproc variable
        # otherwise variable is hardware variable of function pointer type
        p = PyBytecodeInPreproc
        # instanciation and configuration of crc hardblock functions
        crcStepFn = p(CrcStepHardblock(
            POLY.without_XOROUT(), b8_t,
            maxBytesProcessedInParallel=self.CRC_MAX_BYTES_PROCESSED_IN_PARALLEL))
        crcFinalizeFn = p(CrcFinalizeHardblock(POLY.without_REFOUT()))

        PyBytecodeBlockLabel("bb.entry")
        while b1:
            PyBytecodeBlockLabel("bb.rx.sof")
            rx.readStartOfFrame()
            # for each packet
            crcAcc = HBits(POLY.WIDTH).from_py(POLY.INIT)
            while b1:  # for each byte
                # read 1B and update hasher state, the function of crc are expanded during loop
                # unrolling and there should be just 1 wide call of crcStepFn at the end
                byte = rx.read(b8_t)
                crcAcc = crcStepFn(crcAcc, byte.data)
                if byte.last:
                    PyBytecodeBlockLabel("bb.rx.eof.break")
                    break
                # unroll to match throughput of self.rx
                PyBytecodeStreamLoopUnroll(self.rx)
            PyBytecodeBlockLabel("bb.crcOut")
            rx.readEndOfFrame()
            # apply finalization step which is specific to crc configuration sadfas
            hls.write(crcFinalizeFn(crcAcc), self.tx)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SCrc32_TC(BaseAxi4SPktInScalarOutTC):

    def _test(self, inputs: list[bytes], DATA_WIDTH:int):
        ref = [crc32(inp) & mask(32) for inp in inputs]
        dut = Axi4SCrc32()
        dut.DATA_WIDTH = DATA_WIDTH
        refFramesIn = [[c for c in inp] for inp in inputs]
        super()._test(dut, refFramesIn, ref, platformKwargs=dict(
            debugFilter=HlsDebugBundle.ALL_RELIABLE,
            runTestAfterEachPass=True,
            ))

    def test_1B(self):
        inp = [b"a",
               b"ab", b"abc"
                ]
        self._test(inp, 8)

    def test_2B(self):
        inp = [b"a", b"ab", b"abc", b"abcdefg"]
        self._test(inp, 16)

    def test_4B(self):
        inp = [b"a", b"ab", b"abc", b"abcd", b"abcdefg"]
        self._test(inp, 32)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    import sys
    sys.setrecursionlimit(int(1e6))

    m = Axi4SCrc32()
    m.CRC_MAX_BYTES_PROCESSED_IN_PARALLEL = 2
    m.DATA_WIDTH = 2 * 8
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                           llvmCliArgs=[
                               # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                               # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                               # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::HwtHlsInstCombinePass"),
                           ]
                           )
    import time
    start_time = time.time()
    print(to_rtl_str(m, target_platform=p))
    print("--- %s seconds ---" % (time.time() - start_time))

    import unittest
    testLoader = unittest.TestLoader()
    # suite = testLoader.loadTestsFromTestCase(Axi4SCrc32_TC)
    suite = unittest.TestSuite([Axi4SCrc32_TC("test_4B")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
