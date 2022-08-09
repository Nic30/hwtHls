from typing import Union

from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.ioProxyStream import IoProxyStream
from hwtHls.io.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.io.axiStream.stmWrite import HlsStmWriteAxiStream
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class IoProxyAxiStream(IoProxyStream):

    def __init__(self, hls:"HlsScope", interface:AxiStream):
        IoProxyStream.__init__(self, hls, interface)

    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxiStream(self.hls, self.interface, dtype, reliable)

    def write(self, v:Union[HValue, RtlSignal, SsaValue, Interface]):
        return HlsStmWriteAxiStream(self.hls, v, self.interface)
