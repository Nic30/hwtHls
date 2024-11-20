from typing import Union

from hwt.hdl.const import HConst
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.amba.axi4Stream.metadata import addAxi4StreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument, BasicBlock
from hwtLib.amba.axi4s import Axi4Stream
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO


class HlsStmWriteAxi4Stream(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[RtlSignal, HConst],
        dst:Axi4Stream):
        HlsWrite.__init__(self, parent, src, dst, src._dtype)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        toLlvm.addAfterTranslationUnique(addAxi4StreamLllvmMetadata)
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self, True)
        dst: Argument
        bb, src = toLlvm._translateExprToLlvm(bb, self.getSrc())
        return bb, toLlvm.b.CreateStreamWrite(dst, src)
