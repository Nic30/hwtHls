from hwtHls.ssa.llvm.llvmIr import runOpt
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaPassRunLlvmOpt(SsaPass):

    def apply(self, hls:"HlsStreamProc", to_ssa:"AstToSsa"):
        toLlvm: ToLlvmIrTranslator = to_ssa.start
        runOpt(toLlvm.main)
