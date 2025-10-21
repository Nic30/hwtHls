from typing import Union, Optional

from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.statementsWrite import HlsWrite
from hwtHls.llvm.llvmIr import Argument, BasicBlock
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO
from hwtLib.avalon.st import AvalonST


class HlsStmWriteAvalonSt(HlsWrite):

    def __init__(self,
        ioProxy: "IoProxyAvalonSt",
        src: Union[RtlSignal, HConst],
        empty: Optional[Union[RtlSignal, HConst]],
        sof: Optional[Union[RtlSignal, HConst]],
        eof: Optional[Union[RtlSignal, HConst]],
        dst: AvalonST,
        mayBecomeFlushable: bool=True):
        HlsWrite.__init__(self, ioProxy, src, dst, src._dtype,
                          # True,  # isBlocking
                          True,  # isVolatile
                          mayBecomeFlushable=mayBecomeFlushable)
        self.empty = empty
        self.sof = sof
        self.eof = eof

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self._ioProxy, self, True)
        dst: Argument
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)

        if isinstance(self.empty, int):
            _dst: AvalonST = self.dst
            widthOfEmpty = _dst._getWidthOfEmptyForSelf()
        else:
            widthOfEmpty = None

        bb, empty = toLlvm._translateOptionalIntOrExpr(bb, self.empty, widthOfEmpty)
        bb, sof = toLlvm._translateOptionalIntOrExpr(bb, self.sof, 1)
        bb, eof = toLlvm._translateOptionalIntOrExpr(bb, self.eof, 1)

        return bb, toLlvm.b.CreateStreamWrite(dst, src, empty, sof, eof)
