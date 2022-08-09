from typing import Union

from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.value import SsaValue
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteStartOfFrame, \
    HlsStmWriteEndOfFrame


class IoProxyStream(object):
    '''
    An object which builds the stream access statements.
    '''

    def __init__(self, hls: "HlsScope", interface: Interface):
        self.hls = hls
        self.interface = interface

    def readStartOfFrame(self):
        return HlsStmReadStartOfFrame(self.hls, self.interface)

    def read(self, t: HdlType, reliable=True):
        """
        :param reliable: if true the it is expected that the stream never ends prematurely and the check is ommited
                         if false there is a check if the data is actually present
        """
        raise NotImplementedError("Must be implemented in an implementation of this class for the specific interface")
        
    def readEndOfFrame(self):
        return HlsStmReadEndOfFrame(self.hls, self.interface)
    
    def writeStartOfFrame(self):
        return HlsStmWriteStartOfFrame(self.hls, self.interface)

    def write(self, v: Union[HValue, RtlSignal, SsaValue, Interface]):
        raise NotImplementedError("Must be implemented in an implementation of this class for the specific interface")

    def writeEndOfFrame(self):
        return HlsStmWriteEndOfFrame(self.hls, self.interface)
