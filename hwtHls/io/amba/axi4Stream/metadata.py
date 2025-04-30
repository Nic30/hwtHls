from hwtHls.llvm.llvmIr import Function
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented
from hwtLib.amba.axi4s import Axi4Stream


def addAxi4StreamLllvmMetadata(tr: ToLlvmIrTranslator):
    """
    This prepares hwtHls.streamIo metadata which is composed of tuples for StreamChannelFormatInfo
    """
    F: Function = tr.llvm.main
    ioMetaTuples = []
    for i, (io, _, _, reads, writes) in enumerate(tr.ioSorted):
        assert reads or writes, ("io does not have any read or write", io)
        if isinstance(io, (Axi4Stream, Axi4StreamSegmented)):
            ioArgIndex = tr.mdGetUInt32(i)
            isOutput = tr.mdGetUInt32(bool(writes))
            byteWidth = tr.mdGetUInt32(8)
            if isinstance(io, Axi4Stream):
                io: Axi4Stream
                dataWidth = tr.mdGetUInt32(io.DATA_WIDTH)
                byteEnableEncoding = tr.mdGetStr("mask" if (io.USE_STRB or io.USE_KEEP) else "none")
                supportZLP = tr.mdGetUInt32(0)
                framingEncoding = tr.mdGetStr("eof")
                errorWidth = tr.mdGetUInt32(io.USER_WIDTH)
                segmentCnt = tr.mdGetUInt32(1)
            else:
                io: Axi4StreamSegmented
                assert isinstance(io, Axi4StreamSegmented), io
                dataWidth = tr.mdGetUInt32(io.SEGMENT_DATA_WIDTH)
                byteEnableEncoding = tr.mdGetStr("enable+empty")
                supportZLP = tr.mdGetUInt32(io.SUPPORT_ZLP)
                framingEncoding = tr.mdGetStr("sof+eof" if io.USE_SOF else "eof")
                errorWidth = tr.mdGetUInt32(io.ERROR_WIDTH)
                segmentCnt = tr.mdGetUInt32(io.SEGMENT_CNT)

            ioMetaTuples.append(
                           tr.mdGetTuple([ioArgIndex,
                                          isOutput,
                                          dataWidth,
                                          byteWidth,
                                          byteEnableEncoding,
                                          supportZLP,
                                          framingEncoding,
                                          errorWidth,
                                          segmentCnt,
                                          ], False))

    assert ioMetaTuples, "If there is no axi stream interface there was no reason to call this function"
    F.setMetadata(tr.strCtx.addStringRef("hwtHls.streamIo"),
                  tr.mdGetTuple(ioMetaTuples, False))
