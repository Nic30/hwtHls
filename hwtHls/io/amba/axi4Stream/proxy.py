from typing import Union, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioProxyStream import IoProxyStream
from hwtHls.frontend.pyBytecode import hlsLowLevel
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream, \
    HlsStmReadAxi4StreamSegmented
from hwtHls.io.amba.axi4Stream.stmWrite import HlsStmWriteAxi4Stream, \
    HlsStmWriteAxi4StreamSegmented
from hwtHls.llvm.llvmIr import Value, MDTuple, StreamChannelFormatInfo
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream


class IoProxyAxi4Stream(IoProxyStream):
    """
    :see: :class:`~.IoProxyStream`
    """

    def __init__(self, hls:"HlsScope", hwio:Axi4Stream):
        IoProxyStream.__init__(self, hls, hwio)
        commonIo = [hwio.data,
                    hwio.ready,
                    hwio.valid,
                    getattr(hwio, "strb", None),
                    getattr(hwio, "keep", None),
                    getattr(hwio, "last", None),
                    getattr(hwio, "user", None),
                    getattr(hwio, "error", None),
                    ]
        for _hwio in hwio._hwIOs:
            assert _hwio in commonIo, ("Must not contain any non-standard signals, (use user signal to store this)", hwio, _hwio)

    @override
    @hlsLowLevel
    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxi4Stream(self, self.interface, dtype, reliable)

    @override
    @hlsLowLevel
    def write(self, v:Union[HConst, RtlSignal, Value, HwIO],
              empty:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              sof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              user:Union[None, HConst, RtlSignal, Value, HwIO]=None):
        if empty is not None:
            raise NotImplementedError("Convert empty to mask because this interface uses mask")
        return HlsStmWriteAxi4Stream(self, v, mask, sof, eof, user, self.interface)

    @override
    def _getLlvmIoProtocolMetadata(self, tr: "ToLlvmIrTranslator") -> Optional[MDTuple]:
        """
        This prepares HwtHlsIoMetadata.ioProtocolMd metadata which is composed of tuples for StreamChannelFormatInfo
        """
        byteWidth = tr.mdGetUInt32(8)
        io: Axi4Stream = self.interface

        dataWidth = tr.mdGetUInt32(io.DATA_WIDTH)
        hasMask = io.USE_STRB or io.USE_KEEP
        byteEnableEncoding = tr.mdGetStr("mask" if hasMask else "none")
        supportZLP = tr.mdGetUInt32(int(io.DATA_WIDTH == 8 and hasMask))
        framingEncoding = tr.mdGetStr("eof")
        errorWidth = tr.mdGetUInt32(0)
        userWidth = tr.mdGetUInt32(io.USER_WIDTH)
        segmentCnt = tr.mdGetUInt32(1)

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

    @override
    @classmethod
    def _getRtlSyncSignals(cls, src: Axi4Stream, formatAsValidReadyTuple=True):
        return (src.valid, src.ready)


class IoProxyAxi4StreamSegmented(IoProxyStream):
    """
    :see: :class:`~.IoProxyStream`
    :note: maybe interesting https://cesnet.github.io/ofm/mfb.html
    """

    def __init__(self, hls:"HlsScope", hwio:Axi4StreamSegmented):
        IoProxyStream.__init__(self, hls, hwio)
        commonIo = [
            hwio.data,
            hwio.ready,
            hwio.valid,
            hwio.user,
        ]
        for _hwio in hwio._hwIOs:
            assert _hwio in commonIo, ("Must not contain any non-standard signals, (use SEGMENT_USER_T to store this)", hwio, _hwio)

    @override
    @hlsLowLevel
    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxi4StreamSegmented(self, self.interface, dtype, reliable)

    @override
    @hlsLowLevel
    def write(self, v:Union[HConst, RtlSignal, Value, HwIO],
              empty:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              sof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              user:Union[None, HConst, RtlSignal, Value, HwIO]=None):
        """
        :see: :meth:`IoProxyStream.write`
        """
        if mask is not None:
            raise NotImplementedError("convert mask to empty because this interface uses empty")
        return HlsStmWriteAxi4StreamSegmented(self, v, empty, sof, eof, user, self.interface)

    @override
    def _getLlvmIoProtocolMetadata(self, tr: "ToLlvmIrTranslator") -> Optional[MDTuple]:
        """
        This prepares HwtHlsIoMetadata.ioProtocolMd metadata which is composed of tuples for StreamChannelFormatInfo
        """
        byteWidth = tr.mdGetUInt32(8)
        io: Axi4StreamSegmented = self.interface
        dataWidth = tr.mdGetUInt32(io.SEGMENT_DATA_WIDTH)
        byteEnableEncoding = tr.mdGetStr("enable+empty")
        supportZLP = tr.mdGetUInt32(io.SUPPORT_ZLP)
        framingEncoding = tr.mdGetStr("sof+eof" if io.USE_SOF else "eof")
        errorWidth = tr.mdGetUInt32(io.ERROR_WIDTH)
        userWidth = tr.mdGetUInt32(0 if io.SEGMENT_USER_T is None else io.SEGMENT_USER_T.bit_length())
        segmentCnt = tr.mdGetUInt32(io.SEGMENT_CNT)
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

    @override
    @classmethod
    def _getRtlSyncSignals(cls, src: Axi4StreamSegmented, formatAsValidReadyTuple=True):
        return IoProxyAxi4Stream._getRtlSyncSignals(src, formatAsValidReadyTuple=formatAsValidReadyTuple)
