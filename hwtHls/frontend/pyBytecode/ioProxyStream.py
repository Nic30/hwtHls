from typing import Union

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.statementsWrite import HlsStmWriteStartOfFrame, \
    HlsStmWriteEndOfFrame
from hwtHls.llvm.llvmIr import Value


class IoProxyStream(object):
    '''
    An object which builds the stream access statements.
    
    :attention: The readStartOfFrame, readEndOfFrame, writeStartOfFrame, writeEndOfFrame
        are not controlling the packet creation. They do not translate to any physical operation,
        instead they are markers in code which is used as a boundary for detector of packet communication.
        E.g. writeEndOfFrame does not produce last word of data with end-of-frame flag, but instead
        it tells that at this position in code there must have been previous write with eof=1. 
    '''

    def __init__(self, hls: "HlsScope", interface: HwIO):
        self.hls = hls
        self.interface = interface
        self.name = interface._name

    def readStartOfFrame(self):
        ":see: :class:`~.HlsStmReadStartOfFrame`"
        return HlsStmReadStartOfFrame(self.hls, self.interface)

    def read(self, t: HdlType, reliable=True):
        """
        :param reliable: if true the it is expected that the stream never ends prematurely and the check is ommited
                         if false there is a check if the data is actually present
        """
        raise NotImplementedError("Must be implemented in an implementation of this class for the specific interface")

    def readEndOfFrame(self):
        ":see: :class:`~.HlsStmReadEndOfFrame`"
        return HlsStmReadEndOfFrame(self.hls, self.interface)

    def writeStartOfFrame(self, mayBecomeFlushable=False):
        """
        :see: :class:`~.HlsStmWriteStartOfFrame`
        :param mayBecomeFlushable: :see: :class:`~.HlsNetNodeWrite`
        """
        return HlsStmWriteStartOfFrame(self.hls, self.interface, mayBecomeFlushable=mayBecomeFlushable)

    def write(self, v: Union[HConst, RtlSignal, Value, HwIO],
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None):
        """
        :param v: data to write
        :param mask: mask which signalizes which byte of data is valid
            it may have 0 prefix when this is first word or 0 suffix if this
            last word, otherwise it must be all ones
        :param eof: input end-of-frame to write
        
        """
        raise NotImplementedError("Must be implemented in an implementation of this class for the specific interface")

    def writeEndOfFrame(self):
        ":see: :class:`~.HlsStmWriteEndOfFrame`"
        return HlsStmWriteEndOfFrame(self.hls, self.interface)
