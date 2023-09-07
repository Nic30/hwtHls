from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpMIR(SsaPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", toSsa: "HlsAstToSsa"):
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        mf = tr.llvm.getMachineFunction(tr.llvm.main)
        assert mf
        out, doClose = self.outStreamGetter(tr.llvm.main.getGlobalIdentifier())
        try:
            out.write(mf.serialize())
        finally:
            if doClose:
                out.close()
