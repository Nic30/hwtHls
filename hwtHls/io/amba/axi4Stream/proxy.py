from typing import Union, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioProxyScalar import IoProxyScalar
from hwtHls.frontend.ioProxyStream import IoProxyStream
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream, \
    HlsStmReadAxi4StreamSegmented
from hwtHls.io.amba.axi4Stream.stmWrite import HlsStmWriteAxi4Stream, \
    HlsStmWriteAxi4StreamSegmented
from hwtHls.llvm.llvmIr import Value, HwtHlsIoMetadata
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream


class IoProxyAxi4Stream(IoProxyStream):
    """
    :see: :class:`~.IoProxyStream`
    """

    def __init__(self, hls:"HlsScope", interface:Axi4Stream):
        IoProxyStream.__init__(self, hls, interface)

    def getNativeTypeOfHwIoWithoutSyncSignals(self, src: HwIO):
        return IoProxyScalar.getNativeTypeOfHwIoWithoutSyncSignals(self, src)

    @override
    def getDataTypeOfNativeRead(self) -> HdlType:
        return IoProxyScalar.getDataTypeOfNativeRead(self)

    @override
    def getDataTypeOfNativeWrite(self) -> HdlType:
        return IoProxyScalar.getDataTypeOfNativeWrite(self)

    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxi4Stream(self.hls, self.interface, dtype, reliable)

    def write(self, v:Union[HConst, RtlSignal, Value, HwIO],
              empty:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              sof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None):
        if empty is not None:
            raise NotImplementedError("Convert empty to mask because this interface uses mask")
        return HlsStmWriteAxi4Stream(self.hls, v, mask, sof, eof, self.interface)

    @override
    def _translateMirToNetlist_HWTFPGA_CLOAD(self, *args, **kwargs) -> Sequence[HlsNetNode]:
        return IoProxyScalar._translateMirToNetlist_HWTFPGA_CLOAD(self, *args, **kwargs)

    @override
    def _translateMirToNetlist_HWTFPGA_CSTORE(self, *args, **kwargs) -> Sequence[HlsNetNode]:
        return IoProxyScalar._translateMirToNetlist_HWTFPGA_CSTORE(self, *args, **kwargs)

    @override
    def updateLlvmHwtHlsIoMetadata(self, tr: "ToLlvmIrTranslator", md: HwtHlsIoMetadata) -> bool:
        """
        This prepares HwtHlsIoMetadata.streamIoMd metadata which is composed of tuples for StreamChannelFormatInfo
        """
        byteWidth = tr.mdGetUInt32(8)
        io: Axi4Stream = self.interface

        dataWidth = tr.mdGetUInt32(io.DATA_WIDTH)
        hasMask = io.USE_STRB or io.USE_KEEP
        byteEnableEncoding = tr.mdGetStr("mask" if hasMask else "none")
        supportZLP = tr.mdGetUInt32(int(io.DATA_WIDTH == 8 and hasMask))
        framingEncoding = tr.mdGetStr("eof")
        errorWidth = tr.mdGetUInt32(io.USER_WIDTH)
        segmentCnt = tr.mdGetUInt32(1)

        md.streamIoMd = tr.mdGetTuple([
                                      dataWidth,
                                      byteWidth,
                                      byteEnableEncoding,
                                      supportZLP,
                                      framingEncoding,
                                      errorWidth,
                                      segmentCnt,
                                      ], False)
        return True

        # if changed and F.getMetadata(tr.strCtx.addStringRef(HwtHlsIoMetadata.METADATA_NAME)) is not None:
        #    addHwtHlsFunctionIoMetadata(tr)  # update current metadata
        # # else assume that the metadata will be set later


class IoProxyAxi4StreamSegmented(IoProxyStream):
    """
    :see: :class:`~.IoProxyStream`
    :note: maybe interesting https://cesnet.github.io/ofm/mfb.html
    """

    def __init__(self, hls:"HlsScope", interface:Axi4Stream):
        IoProxyStream.__init__(self, hls, interface)

    def read(self, dtype:HdlType, reliable=True):
        return HlsStmReadAxi4StreamSegmented(self.hls, self.interface, dtype, reliable)

    def write(self, v:Union[HConst, RtlSignal, Value, HwIO],
              empty:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              mask:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              sof:Union[None, HConst, RtlSignal, Value, HwIO]=None,
              eof:Union[None, HConst, RtlSignal, Value, HwIO]=None):
        if mask is not None:
            raise NotImplementedError("convert mask to empty because this interface uses empty")
        return HlsStmWriteAxi4StreamSegmented(self.hls, v, empty, sof, eof, self.interface)

    @override
    def updateLlvmHwtHlsIoMetadata(self, tr: "ToLlvmIrTranslator", md: HwtHlsIoMetadata) -> bool:
        """
        This prepares HwtHlsIoMetadata.streamIoMd metadata which is composed of tuples for StreamChannelFormatInfo
        """
        byteWidth = tr.mdGetUInt32(8)
        io: Axi4StreamSegmented = self.interface
        dataWidth = tr.mdGetUInt32(io.SEGMENT_DATA_WIDTH)
        byteEnableEncoding = tr.mdGetStr("enable+empty")
        supportZLP = tr.mdGetUInt32(io.SUPPORT_ZLP)
        framingEncoding = tr.mdGetStr("sof+eof" if io.USE_SOF else "eof")
        errorWidth = tr.mdGetUInt32(io.ERROR_WIDTH)
        segmentCnt = tr.mdGetUInt32(io.SEGMENT_CNT)
        md.streamIoMd = tr.mdGetTuple([
                                      dataWidth,
                                      byteWidth,
                                      byteEnableEncoding,
                                      supportZLP,
                                      framingEncoding,
                                      errorWidth,
                                      segmentCnt,
                                      ], False)
        return True
