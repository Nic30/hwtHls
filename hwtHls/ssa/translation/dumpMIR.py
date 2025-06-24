import os

from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import MachineFunction
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpMIR(SsaAnalysisPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toLlvm:"ToLlvmIrTranslator", mf: MachineFunction):
        dumpFilename = mf.getName().str()
        if toLlvm._dbgSubDir:
            dumpFilename = os.path.join(toLlvm._dbgSubDir, dumpFilename)
        out, doClose = self.outStreamGetter(dumpFilename)
        try:
            out.write(mf.serialize())
        finally:
            if doClose:
                out.close()
