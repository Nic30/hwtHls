from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.typingFuture import override


class SsaPassDumpMIR(SsaPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toSsa:"HlsAstToSsa"):
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
