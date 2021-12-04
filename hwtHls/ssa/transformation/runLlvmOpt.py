from hwtHls.llvm.toLlvm import runOpt
from hwtHls.llvm.toLlvmPy import ToLlvmIrTranslator
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaPassRunLlvmOpt(SsaPass):

    def apply(self, hls:"HlsStreamProc", to_ssa:"AstToSsa"):
        toLlvm: ToLlvmIrTranslator = to_ssa.start
        runOpt(toLlvm.main)
