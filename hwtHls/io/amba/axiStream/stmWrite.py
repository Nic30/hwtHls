from typing import Union

from hwt.hdl.value import HValue
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.amba.axiStream.metadata import addAxiStreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axis import AxiStream


class HlsStmWriteAxiStream(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[SsaValue, HValue],
        dst:AxiStream):
        HlsWrite.__init__(self, parent, src, dst, src._dtype)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        toLlvm.addAfterTranslationUnique(addAxiStreamLllvmMetadata)
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        src = toLlvm._translateExpr(self.getSrc())
        return toLlvm.b.CreateStreamWrite(dst, src)
