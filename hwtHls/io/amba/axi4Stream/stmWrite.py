from typing import Union

from hwt.hdl.const import HConst
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.amba.axi4Stream.metadata import addAxi4StreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi4s import Axi4Stream


class HlsStmWriteAxi4Stream(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[SsaValue, HConst],
        dst:Axi4Stream):
        HlsWrite.__init__(self, parent, src, dst, src._dtype)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        toLlvm.addAfterTranslationUnique(addAxi4StreamLllvmMetadata)
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        src = toLlvm._translateExpr(self.getSrc())
        return toLlvm.b.CreateStreamWrite(dst, src)
