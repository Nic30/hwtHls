from typing import Union, Optional

from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.llvm.llvmIr import Argument, BasicBlock
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.amba.axi4SSegmented import Axi4StreamSegmented


class HlsStmWriteAxi4Stream(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[RtlSignal, HConst],
        mask:Optional[Union[RtlSignal, HConst]],
        sof:Optional[Union[RtlSignal, HConst]],
        eof:Optional[Union[RtlSignal, HConst]],
        dst:Axi4Stream,
        mayBecomeFlushable:bool=True):
        HlsWrite.__init__(self, parent, src, dst, src._dtype,
                          # True, # isBlocking,
                          True,  # isVolatile
                          mayBecomeFlushable=mayBecomeFlushable)
        self.mask = mask
        self.sof = sof
        self.eof = eof

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, True)
        dst: Argument
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)
        bb, mask = toLlvm._translateOptionalIntOrExpr(bb, self.mask, self.dst.DATA_WIDTH // 8)
        bb, sof = toLlvm._translateOptionalIntOrExpr(bb, self.sof, 1)
        bb, eof = toLlvm._translateOptionalIntOrExpr(bb, self.eof, 1)
        return bb, toLlvm.b.CreateStreamWrite(dst, src, mask, sof, eof)


class HlsStmWriteAxi4StreamSegmented(HlsWrite):

    def __init__(self,
        parent:"HlsScope",
        src:Union[RtlSignal, HConst],
        empty:Optional[Union[RtlSignal, HConst]],
        sof:Optional[Union[RtlSignal, HConst]],
        eof:Optional[Union[RtlSignal, HConst]],
        dst:Axi4Stream,
        mayBecomeFlushable:bool=True):
        HlsWrite.__init__(self, parent, src, dst, src._dtype,
                          # True,  # isBlocking
                          True,  # isVolatile
                          mayBecomeFlushable=mayBecomeFlushable)
        self.empty = empty
        self.sof = sof
        self.eof = eof

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, True)
        dst: Argument
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)

        if isinstance(self.empty, int):
            _dst: Axi4StreamSegmented = self.dst
            widthOfEmpty = _dst._getWidthOfEmpty(
                src.getType().getIntegerBitWidth(), _dst.BYTE_WIDTH, _dst.SUPPORT_ZLP)
        else:
            widthOfEmpty = None

        bb, empty = toLlvm._translateOptionalIntOrExpr(bb, self.empty, widthOfEmpty)
        bb, sof = toLlvm._translateOptionalIntOrExpr(bb, self.sof, 1)
        bb, eof = toLlvm._translateOptionalIntOrExpr(bb, self.eof, 1)

        return bb, toLlvm.b.CreateStreamWrite(dst, src, empty, sof, eof)
