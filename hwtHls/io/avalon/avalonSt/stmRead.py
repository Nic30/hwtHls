from math import ceil
from typing import Optional

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.hwIOStruct import HwIO_to_HdlType, HwIOStruct
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtLib.avalon.st import AvalonST


class HlsStmReadAvalonSt(HlsStmReadAxi4Stream):
    """
    A statement used for reading of chunk of data from AvalonST interface.
    
    :see: HlsStmReadAxi4Stream
    """

    def __init__(self,
                 ioProxy: "IoProxyAvalonSt",
                 src: AvalonST,
                 dtype: HdlType,
                 isReliable: bool):
        if src.firstSymbolInHighOrderBits:
            raise NotImplementedError("AvalonST in big-endian mode")
        HlsStmReadAxi4Stream.__init__(self, ioProxy, src, dtype, isReliable)

    @override
    def _constructTypeOfInterfaceData(self, src: AvalonST, dtype: HdlType):
        """
        :see: :meth:`HlsStmReadAxi4Stream._constructTypeOfInterfaceData`
        """
        if src.maxChannel:
            raise NotImplementedError()
        if src.readyLatency:
            raise NotImplementedError()
        if src.readyAllowance:
            raise NotImplementedError()
        if src.packetsPerClock > 1:
            raise NotImplementedError()

        # :note: empty is present even if src.USE_EMPTY==False, (if USE_EMPTY==False it is 0 for reliable reads, and non-zero for unreliable reads with underflow)
        if not self._isReliable:
            data_w = dtype.bit_length()
            assert data_w % src.dataBitsPerSymbol == 0, (data_w, src.dataBitsPerSymbol)
            mask_w = ceil(dtype.bit_length() / src.dataBitsPerSymbol)
            emptyT = HBits(log2ceil(mask_w))

        trueDtype = HStruct(
            (dtype, "data"),
            *(((emptyT, "empty"),) if not self._isReliable else ()),
            *(((HBits(src.ERROR_WIDTH), "error"),) if src.ERROR_WIDTH else ()),
            (BIT, "sof"),
            (BIT, "eof"),  # we do not know how many words this read could be,
                           # the eof is disjunction of eof signals from each word
        )
        return trueDtype

    def _copyRtlSignalsToSelf(self, sig: HwIOStruct):
        """
        :see: :meth:`HlsStmReadAxi4Stream._copyRtlSignalsToSelf`
        """
        self.eof: RtlSignal
        self.empty: Optional[RtlSignal]
        for field_path, fieldHwIO in sig._fieldsToHwIOs.items():
            if len(field_path) == 1:
                n = field_path[0]
                assert not hasattr(self, n), (self, n)
                setattr(self, n, fieldHwIO)

    @staticmethod
    def _getWordType(hwIO: AvalonST):
        return HwIO_to_HdlType().apply(hwIO, exclude={hwIO.rd, hwIO.vld})

    def _isSoF(self):
        return self.sof

    def _isEoF(self):
        """
        :return: an expression which is 1 if this is a last word in the frame
        """
        return self.eof

    def _isValid(self):
        """
        :return: an expression which is 1 if all bytes of data are marked valid by mask (strb/keep)
        """
        src = self._src
        if src.USE_EMPTY:
            return src.empty._eq(0)
        else:
            return b1

