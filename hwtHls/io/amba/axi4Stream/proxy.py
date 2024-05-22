from typing import Union

from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.const import HConst
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.ioProxyStream import IoProxyStream
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.io.amba.axi4Stream.stmWrite import HlsStmWriteAxi4Stream
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4s import Axi4Stream


class IoProxyAxi4Stream(IoProxyStream):

    def __init__(self, hls:"HlsScope", interface:Axi4Stream):
        IoProxyStream.__init__(self, hls, interface)

    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxi4Stream(self.hls, self.interface, dtype, reliable)

    def write(self, v:Union[HConst, RtlSignal, SsaValue, HwIO]):
        return HlsStmWriteAxi4Stream(self.hls, v, self.interface)
