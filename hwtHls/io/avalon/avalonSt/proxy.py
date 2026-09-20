from typing import Union, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioProxyStream import IoProxyStream
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.io.avalon.avalonSt.stmRead import HlsStmReadAvalonSt
from hwtHls.io.avalon.avalonSt.stmWrite import HlsStmWriteAvalonSt
from hwtHls.llvm.llvmIr import Value, StreamChannelFormatInfo, MDTuple
from hwtLib.avalon.st import AvalonST


class IoProxyAvalonSt(IoProxyStream):
    """
    :see: :class:`~.IoProxyStream`
    """

    def __init__(self, hls:"HlsScope", hwio:AvalonST):
        commonIo = [
            hwio.data,
            getattr(hwio, "empty", None),
            getattr(hwio, "error", None),
            getattr(hwio, "user", None),
            getattr(hwio, "startOfPacket", None),
            getattr(hwio, "endOfPacket", None),
            hwio.rd,
            hwio.vld,
        ]
        for _hwio in hwio._hwIOs:
            assert _hwio in commonIo, ("Must not contain any non-standard signals, (use user signal instead)", hwio, _hwio)

        if hwio.firstSymbolInHighOrderBits:
            raise NotImplementedError("AvalonST in big-endian mode")

        IoProxyStream.__init__(self, hls, hwio)

    @override
    @hlsLowLevel
    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAvalonSt(self, self.interface, dtype, reliable)

    @override
    @hlsLowLevel
    def write(self, v:Union[HConst, RtlSignal, Value, HwIO],
              empty:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              sof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              error:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              user:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              ):
        """
        :param extraValues: the kwargs to specify values for non-std signals potentially defined on target AvalonST
        """
        if mask is not None:
            raise NotImplementedError("convert mask to empty because this interface uses empty")
        return HlsStmWriteAvalonSt(self, v, empty, sof, eof, error, user, self.interface)

    @override
    def _getLlvmIoProtocolMetadata(self, tr: "ToLlvmIrTranslator") -> Optional[MDTuple]:
        """
        This prepares HwtHlsIoMetadata.streamIoMd metadata which is composed of tuples for StreamChannelFormatInfo
        """
        io: AvalonST = self.interface
        byteWidth = tr.mdGetUInt32(io.dataBitsPerSymbol)
        assert io.DATA_WIDTH % io.dataBitsPerSymbol == 0
        dataWidth = tr.mdGetUInt32(io.DATA_WIDTH // io.packetsPerClock)
        byteEnableEncoding = tr.mdGetStr("enable+empty")
        supportZLP = tr.mdGetUInt32(io.SUPPORT_ZLP)
        framingEncoding = tr.mdGetStr("sof+eof")
        errorWidth = tr.mdGetUInt32(io.ERROR_WIDTH)
        userWidth = tr.mdGetUInt32(0 if io.USER_T is None else io.USER_T.bit_length())
        segmentCnt = tr.mdGetUInt32(io.packetsPerClock)
        return tr.mdGetTuple([
            tr.mdGetStr(StreamChannelFormatInfo.METADATA_NAME),
            dataWidth,
            byteWidth,
            byteEnableEncoding,
            supportZLP,
            framingEncoding,
            errorWidth,
            userWidth,
            segmentCnt,
            ], False)
        return True

    @override
    @staticmethod
    def _getRtlSyncSignals(src: AvalonST, formatAsValidReadyTuple=True):
        return (src.vld, src.rd)
