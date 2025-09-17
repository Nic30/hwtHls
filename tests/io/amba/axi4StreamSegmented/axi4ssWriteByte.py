#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4StreamSegmented
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from tests.io.amba.axi4Stream.axi4sWriteByte import Axi4SWriteByteOnce, \
    Axi4SWriteByte


class Axi4SSWriteByteOnce(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))
        Axi4StreamSegmented.hwConfig(self)

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        with self._hwParamsShared():
            self.dataOut = Axi4StreamSegmented()._m()

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxi4StreamSegmented(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, Axi4SWriteByteOnce.mainThread, self, dataOut))
        hls.compile()


class Axi4SSWriteByte(Axi4SSWriteByteOnce):

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxi4StreamSegmented(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, Axi4SWriteByte.mainThread, self, dataOut))
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = Axi4SSWriteByte()
    m.SEGMENT_CNT = 1
    m.SEGMENT_DATA_WIDTH = 64
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_AFTER_ALL]
        )
    print(to_rtl_str(m, target_platform=p))
