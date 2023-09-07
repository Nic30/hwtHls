from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtLib.amba.axis import AxiStream
from hwtHls.llvm.llvmIr import Function


def addAxiStreamLllvmMetadata(tr: ToLlvmIrTranslator):
    F: Function = tr.llvm.main
    ioMetaTuples = []
    for i, (_, io, _) in enumerate(tr.ioSorted):
        if isinstance(io, AxiStream):
            ioMetaTuples.append(
                           tr.mdGetTuple([tr.mdGetUInt32(i),
                                          tr.mdGetUInt32(io.DATA_WIDTH),
                                          tr.mdGetUInt32(io.USE_STRB or io.USE_KEEP), ], False))

    assert ioMetaTuples, "If there is no axi stream interface there was no reason to call this function"
    F.setMetadata(tr.strCtx.addStringRef("hwtHls.streamIo"),
                  tr.mdGetTuple(ioMetaTuples, False))
