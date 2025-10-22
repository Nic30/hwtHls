#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.struct import HStruct
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream, \
    IoProxyAxi4StreamSegmented
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.types.ctypes import uint16_t, uint32_t
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParseStructManyInts0, \
    Axi4SParse2fields


class Axi4SSParseStructManyInts0(HwModule):
    AXI_CLS = Axi4StreamSegmented

    @override
    def hwConfig(self) -> None:
        self.SEGMENT_CNT = HwParam(1)
        self.SEGMENT_DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        Axi4SParseStructManyInts0.hwDeclr(self)

    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        PyBytecodeInline(Axi4SParseStructManyInts0.mainThread)(self, hls, i)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        i = IoProxyAxi4StreamSegmented(hls, self.i)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, i))
        hls.compile()


class Axi4SSParseStructManyInts1(Axi4SSParseStructManyInts0):
    """
    :note: :see: :class:`Axi4SParseStructManyInts0`
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        PyBytecodeInline(Axi4SParseStructManyInts0.mainThread)(self, hls, i)


struct_i16_i32 = HStruct(
    (uint16_t, "i16"),
    (uint32_t, "i32"),
)


class Axi4SSParse2fields(Axi4SSParseStructManyInts0):

    @override
    def hwDeclr(self):
        Axi4SParse2fields.hwDeclr(self)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        PyBytecodeInline(Axi4SParse2fields.mainThread)(self, hls, i)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS

    m = Axi4SSParse2fields()
    m.SEGMENT_DATA_WIDTH = 64
    m.SEGMENT_CNT = 2
    p = VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
         llvmCliArgs=[
             LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
             LLVM_CLI_COMMON_OPTS.VERIFY_EACH,
        ])
    print(to_rtl_str(m, target_platform=p))
