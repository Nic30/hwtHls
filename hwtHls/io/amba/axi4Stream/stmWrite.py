from typing import Union, Optional

from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.io.amba.axi4Stream.metadata import addAxi4StreamLllvmMetadata
from hwtHls.llvm.llvmIr import Argument, BasicBlock, Type
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO
from hwtLib.amba.axi4s import Axi4Stream


class HlsStmWriteAxi4Stream(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[RtlSignal, HConst],
        mask:Optional[Union[RtlSignal, HConst]],
        eof:Optional[Union[RtlSignal, HConst]],
        dst:Axi4Stream,
        mayBecomeFlushable:bool=True):
        HlsWrite.__init__(self, parent, src, dst, src._dtype,
                          # True, # isBlocking,
                          True,  # isVolatile
                          mayBecomeFlushable=mayBecomeFlushable)
        self.mask = mask
        self.eof = eof

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        toLlvm.addAfterTranslationUnique(addAxi4StreamLllvmMetadata)
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self, True)
        dst: Argument
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)
        mask = self.mask
        if mask is not None:
            if isinstance(mask, int):
                mask = toLlvm._translateExprInt(mask, Type.getIntNTy(toLlvm.ctx, self.dst.DATA_WIDTH // 8))
            else:
                bb, mask = toLlvm._translateExprToLlvm(bb, mask)

        eof = self.eof
        if eof is not None:
            if isinstance(eof, int):
                eof = toLlvm._translateExprInt(eof, Type.getIntNTy(toLlvm.ctx, 1))
            else:
                bb, eof = toLlvm._translateExprToLlvm(bb, eof)

        return bb, toLlvm.b.CreateStreamWrite(dst, src, mask, eof)
