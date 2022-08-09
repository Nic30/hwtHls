from hwt.hdl.types.defs import BIT
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.axiStream.proxy import IoProxyAxiStream
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint8_t


class AxiSWriteByteOnce(Unit):
    
    def _config(self):
        self.CLK_FREQ = Param(int(100e6))
        AxiStream._config(self)
        
    def _declr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.dataOut = AxiStream()._m()

    def mainThread(self, dataOut: IoProxyAxiStream):
        dataOut.writeStartOfFrame()
        dataOut.write(uint8_t.from_py(1))
        dataOut.writeEndOfFrame()

    def _impl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxiStream(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, dataOut))
        hls.compile()


class AxiSWriteByte(AxiSWriteByteOnce):

    def mainThread(self, dataOut: IoProxyAxiStream):
        while BIT.from_py(1):
            dataOut.writeStartOfFrame()
            dataOut.write(uint8_t.from_py(1))
            dataOut.writeEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSWriteByte()
    u.USE_STRB = True
    u.DATA_WIDTH = 16
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
