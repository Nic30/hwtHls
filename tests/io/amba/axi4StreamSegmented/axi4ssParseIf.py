#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.io.hwIoVectorized import HwIOStructVecRdVld
from hwtHls.scope import HlsScope
from tests.io.amba.axi4Stream.axi4sParseIf import Axi4SParse2If2B, \
    Axi4SParse2IfLess, Axi4SParse2If, Axi4SParse2IfAndSequel
from tests.io.amba.axi4StreamSegmented.axi4ssParseLinear import Axi4SSParse2fields


class Axi4SSParse2If2B(Axi4SSParse2fields):
    """
    :see: :class:`Axi4SSParse2If2B`
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        o: HwIOStructVecRdVld = HwIOStructVecRdVld()._m()
        o.T = HBits(8)
        o.LANE_CNT = self.i.SEGMENT_CNT
        self.o = o

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        PyBytecodeInline(Axi4SParse2If2B.mainThread)(self, hls, i)


class Axi4SSParse2IfLess(Axi4SSParse2fields):
    """
    :see: :class:`Axi4SParse2IfLess`
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        o = HwIOStructVecRdVld()._m()
        o.T = HBits(32)
        o.LANE_CNT = self.i.SEGMENT_CNT
        self.o = o

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        PyBytecodeInline(Axi4SParse2IfLess.mainThread)(self, hls, i)


class Axi4SSParse2If(Axi4SSParse2fields):
    """
    :see: :class:`Axi4SParse2If`
    """

    @override
    def hwDeclr(self):
        Axi4SSParse2IfLess.hwDeclr(self)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        PyBytecodeInline(Axi4SParse2If.mainThread)(self, hls, i)


class Axi4SSParse2IfAndSequel(Axi4SSParse2fields):
    """
    :see: :class:`Axi4SParse2IfAndSequel`
    """

    @override
    def hwConfig(self) -> None:
        Axi4SSParse2fields.hwConfig(self)
        self.WRITE_FOOTER = HwParam(True)

    @override
    def hwDeclr(self):
        Axi4SSParse2IfLess.hwDeclr(self)
        self.o.LANE_CNT *= 2  # because each segment writes 2 words

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        PyBytecodeInline(Axi4SParse2IfAndSequel.mainThread)(self, hls, i)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    # m = Axi4SSParse2If()
    m = Axi4SSParse2IfAndSequel()
    m.WRITE_FOOTER = True

    m.SEGMENT_DATA_WIDTH = 128
    m.SEGMENT_CNT = 4
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                           llvmCliArgs=[
                               # LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
                               # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED
                            ]
                           )
    p._debugExpandCompositeNodes = True
    print(to_rtl_str(m, target_platform=p))
