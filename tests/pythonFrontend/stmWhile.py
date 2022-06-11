from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwtLib.types.ctypes import uint8_t


class HlsPythonHwWhile0(Unit):

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()
        self.i_rst = Signal()

    def mainThread(self, hls: HlsStreamProc):
        i = uint8_t.from_py(0)
        while BIT.from_py(1):  # recognized as HW loop because of type
            i += 1
            hls.write(i, self.o)
            if hls.read(self.i_rst):
                i = 0


    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        mainThread = HlsStreamProcPyThread(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.thread(mainThread)
        hls.compile()


class HlsPythonHwWhile1(HlsPythonHwWhile0):

    def mainThread(self, hls: HlsStreamProc):
        i = uint8_t.from_py(0)
        while BIT.from_py(1):  # recognized as HW loop because of type
            while True:  # recognized as HW loop because of break condition
                hls.write(i, self.o)
                i += 1
                if hls.read(self.i_rst):
                    break

            i = 0



if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = HlsPythonHwWhile1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
    
