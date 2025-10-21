#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Lite import IoProxyAxi4Lite
from hwtHls.llvm.llvmIr import MemoryOrdering
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4Lite import Axi4Lite
from tests.io.bram.bramRead import BramRead


class Axi4LiteCopy(BramRead):
    """
    Sequentially read data from Axi4Lite port and write it using same interface with address after beginning at specified OFFSET.
    """

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        self.ADDR_WIDTH = HwParam(5 + 3)
        self.OFFSET = HwParam(16)  # specified in bus words
        self.SIZE = HwParam(8)  # specified in bus words
        self.DATA_WIDTH = HwParam(64)

    @override
    def hwDeclr(self):
        addClkRstn(self)

        with self._hwParamsShared():
            self.ram: Axi4Lite = Axi4Lite()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, ram: IoProxyAxi4Lite):
        i = ram.indexT.from_py(0)
        while b1:
            PyBytecodeBlockLabel("copyLoop")
            d = ram.read(i).data.data
            # w = ram.wWordT.from_py(None)
            # w.data = d
            # w.strb = mask(w.strb._dtype.bit_length())
            ram.write(i + self.OFFSET // (self.DATA_WIDTH // 8), d)
            if i._eq(self.SIZE - 1):
                i = 0
            else:
                i += 1

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        ram = IoProxyAxi4Lite(hls, self.ram, memOrdering=MemoryOrdering.MEMORDERING_NONE)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, ram)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = Axi4LiteCopy()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED, LLVM_CLI_COMMON_OPTS.VERIFY_EACH]
        )))
