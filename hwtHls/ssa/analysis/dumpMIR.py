from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpMIR():

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa"):
        tr: ToLlvmIrTranslator = to_ssa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        mf = tr.llvm.getMachineFunction(tr.llvm.main)
        assert mf
        out, doClose = self.outStreamGetter(tr.llvm.main.getGlobalIdentifier())
        try:
            out.write(str(mf))
        finally:
            if doClose:
                out.close()
