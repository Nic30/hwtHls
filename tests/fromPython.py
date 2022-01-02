from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython import pyFunctionToSsa
from hwtLib.types.ctypes import uint32_t, uint8_t
from hwt.code import Concat
from hwt.hdl.types.bits import Bits


class HlsConnectionFromPyFn0(Unit):

    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                self.b = self.a

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFn1(Unit):

    def _declr(self):
        self.a = VectSignal(32 - 4, signed=False)
        self.b = VectSignal(32, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                self.b = Concat(self.a, Bits(4).from_py(0))

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnTmpVar(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                a: uint32_t = self.a
                if a == 3:
                    self.b = 10
                else:
                    self.b = 11

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnIf(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                if self.a == 3:
                    self.b = 10
                else:
                    self.b = 11

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnWhile(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                v = uint32_t.from_py(0)
                i = uint8_t.from_py(0)
                while i < 3:
                    v += self.a
                    i += 1
                self.b = v

        hls._thread(*pyFunctionToSsa(hls, mainThread))


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = HlsConnectionFromPyFn1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
