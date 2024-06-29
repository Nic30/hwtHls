#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeLLVMLoopUnroll,\
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class InfLoopUnrollDissable(HwModule):

    @override
    def hwDeclr(self):
        self.o = HwIOVectSignal(8, signed=False)._m()
        addClkRstn(self)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("entry")
        i = uint8_t.from_py(0)
        while BIT.from_py(1):
            PyBytecodeBlockLabel("loopHeader")
            hls.write(i , self.o)
            i += 1
            PyBytecodeLLVMLoopUnroll(False, None)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class InfLoopUnrollCount(InfLoopUnrollDissable):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        PyBytecodeBlockLabel("entry")
        i = uint8_t.from_py(0)
        while BIT.from_py(1):
            PyBytecodeBlockLabel("loopHeader")
            hls.write(i , self.o)
            i += 1
            PyBytecodeLLVMLoopUnroll(True, 3)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = InfLoopUnrollCount()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
