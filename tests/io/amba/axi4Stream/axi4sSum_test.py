#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
from tests.io.amba.axi4Stream._baseAxi4SPktInPktOutTC import BaseAxi4SPktInScalarOutTC
from tests.math.addMasked import AddMaskedHardblock


class Axi4SSum(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = True
            self.tx: HwIODataRdVld = HwIODataRdVld()._m()  # :note: name tx is picked for compatiblity with existing test utilities
            self.tx.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream):
        b8_t = HBits(8)
        # in preproc because variables storing functions must be preproc variable
        # otherwise variable is hardware variable of function pointer type
        p = PyBytecodeInPreproc
        # instanciation and configuration of crc hardblock functions
        addMaskedFn = p(AddMaskedHardblock(b8_t, b8_t))
        PyBytecodeBlockLabel("bb.entry")
        while b1:
            PyBytecodeBlockLabel("bb.rx.sof")
            rx.readStartOfFrame()
            # for each packet
            acc = b8_t.from_py(0)
            while b1:  # for each byte
                # [fixme]
                # code ends up in recognizable format:
                # but HwtHlsInstCombiner::tryReduceMergableFunctionInSelect requres top most (%17) call to have exactly 1 use
                # but in this case it has second user (phi for acc)
                #  %15 = call i8 @hwtHls.pyObjectPlaceholder.0.addMasked.i8.i8(i32 0, i8 %acc, i8 %3, i1 %1) #3
                #  %16 = call i8 @hwtHls.pyObjectPlaceholder.0.addMasked.i8.i8(i32 0, i8 %15, i8 %4, i1 %0) #3
                #  %17 = call i8 @hwtHls.pyObjectPlaceholder.0.addMasked.i8.i8(i32 0, i8 %16, i8 %5, i1 %2) #3
                #  %.mux = select i1 %14, i8 %15, i8 %16
                #  %.mux.mux = select i1 %brmerge, i8 %.mux, i8 %17
                
                
                # read 1B and update hasher state, the function of crc are expanded during loop
                # unrolling and there should be just 1 wide call of crcStepFn at the end
                dataByte = rx.read(b8_t, reliable=False)
                acc = addMaskedFn(acc, dataByte.data, dataByte.strb)
                if dataByte.last:
                    PyBytecodeBlockLabel("bb.rx.eof.break")
                    break
                # unroll to match throughput of self.rx
                PyBytecodeStreamLoopUnroll(self.rx)
            PyBytecodeBlockLabel("bb.out")
            rx.readEndOfFrame()
            hls.write(acc, self.tx)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SSum_TC(BaseAxi4SPktInScalarOutTC):

    def _test(self, inputs: list[list[int]], DATA_WIDTH:int):
        ref = [sum(inp) for inp in inputs]
        dut = Axi4SSum()
        dut.DATA_WIDTH = DATA_WIDTH
        refFramesIn = [[c for c in inp] for inp in inputs]
        super()._test(dut, refFramesIn, ref, platformKwargs=dict(
            # debugFilter=HlsDebugBundle.ALL_RELIABLE,
            # runTestAfterEachPass=True,
            ))

    def test_1B(self):
        inp = [[1],
               [1, 2], [1, 2, 3]
                ]
        self._test(inp, 8)

    def test_2B(self):
        inp = [[1], [1, 2], [1, 2, 3], list(range(1, 7 + 1))]
        self._test(inp, 16)

    def test_4B(self):
        inp = [[1], [1, 2], [1, 2, 3], [1, 2, 3, 4], [1, 2, 3, 4, 5], list(range(1, 7 + 1))]
        self._test(inp, 32)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    import sys
    sys.setrecursionlimit(int(1e6))

    m = Axi4SSum()
    m.DATA_WIDTH = 4 * 8
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                           llvmCliArgs=[
                               LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                               LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                               # LLVM_CLI_COMMON_OPTS.printAfter("hwtHls::HwtHlsInstCombinePass"),
                           ]
                           )
    import time
    start_time = time.time()
    print(to_rtl_str(m, target_platform=p))
    print("--- %s seconds ---" % (time.time() - start_time))

    import unittest
    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(Axi4SSum_TC)
    # suite = unittest.TestSuite([Axi4SSum_TC("test_2B")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)
