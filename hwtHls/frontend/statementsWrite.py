from typing import Union, Tuple, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ioUtils import  ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.frontend.statements import HlsStm
from hwtHls.frontend.statementsRead import HlsRead
from hwtHls.llvm.llvmIr import Argument, Type, ArrayType, TypeToArrayType, \
    Value, BasicBlock, MDTuple
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO


class HlsWrite(HlsStm):
    """
    Container of informations about write in some stream
    """

    def __init__(self,
                 parent: "HlsScope",
                 src:Union[RtlSignal, HConst],
                 dst: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType,
                 isVolatile:bool,
                 mayBecomeFlushable:bool=True,
                 ):
        HlsStm.__init__(self, parent)
        if isinstance(dst, RtlSignal):
            hwIO, indexes, sign_cast_seen = dst._getIndexCascade()
            if hwIO is not dst or indexes:
                raise AssertionError("Use :class:`~.HlsWriteAddressed` if you require addressing", hwIO, indexes, sign_cast_seen)
        else:
            assert not isinstance(dst, (int, HConst)), dst
        self._dtype = dtype
        # [todo] this put this object in temporary inconsistent state,
        #  because src can be more than just SsaValue/HConst instance
        self.src = src
        self._parent = parent
        self._isVolatile = isVolatile
        self._isBlocking = True

        self.dst = dst
        self.mayBecomeFlushable = mayBecomeFlushable

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HlsRead._getInterfaceName(self, io)

    def _translateToLlvm(self, toLlvm: 'ToLlvmIrTranslator', bb: BasicBlock):
        b = toLlvm.b
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)
        # :attention: it is important that dst is evaluated after src expression was translated because Argument
        #  instanced may have been changed by mutateFunctionAddArg
        dst, wordT = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, False)
        dst: Argument
        wordT: Type
        return bb, b.CreateStore(src, dst, self._isVolatile)

    def __repr__(self):
        src = self.src
        return f"<{self.__class__.__name__} {src if isinstance(src, HConst) else src._name}->{HwIO_getName(self._parent.parentHwModule, self.dst)}>"


class HlsWriteAddressed(HlsWrite):

    def __init__(self,
            parent:"HlsScope",
            src:Union[Value, HConst],
            dst:HwIO,
            index: ANY_SCALAR_INT_VALUE,
            element_t: HdlType,
            isVolatile:bool,
            mayBecomeFlushable=True):
        HlsWrite.__init__(self, parent, src, dst, element_t, isVolatile, mayBecomeFlushable=mayBecomeFlushable)
        self.index = index

    def _translateToLlvm(self, toLlvm: 'ToLlvmIrTranslator', bb: BasicBlock):
        b = toLlvm.b
        dst, t = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, False)
        dst: Argument
        t: Type
        bb, src = toLlvm._translateExprToLlvm(bb, self.src)
        # :note: the index type does not matter much as llvm::InstCombine extends it to i64
        index_t = Type.getIntNTy(toLlvm.ctx, 64)  # self.index._dtype.bit_length()
        indexes = [toLlvm._translateExprInt(0, index_t), ]
        bb, index0 = toLlvm._translateExprToLlvm(bb, self.index)
        index0 = toLlvm.b.CreateZExt(index0, index_t)
        indexes.append(index0)

        arrTy: ArrayType = TypeToArrayType(t)
        # elmT = arrTy.getElementType()
        dst = b.CreateInBoundsGEP(arrTy, dst, indexes)

        return bb, b.CreateStore(src, dst, self._isVolatile)

    def __repr__(self):
        src = self.src
        index = self.index
        if isinstance(src, (HwIO, RtlSignal)):
            src = HwIO_getName(self._parent.parentHwModule, src)
        if isinstance(index, (HwIO, RtlSignal)):
            index = HwIO_getName(self._parent.parentHwModule, index)

        return f"<{self.__class__.__name__} {src}->{HwIO_getName(self._parent.parentHwModule, self.dst)}[{index}]>"


class HlsStmWriteStartOfFrame(HlsWrite):
    """
    Statement which marks a start of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", hwIO:HwIO, mayBecomeFlushable:bool=True):
        super(HlsStmWriteStartOfFrame, self).__init__(parent, HVoidOrdering.from_py(None),
                                                      hwIO, HVoidOrdering,
                                                      True,  # isVolatile
                                                      mayBecomeFlushable=mayBecomeFlushable)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, False)
        dst: Argument
        return bb, toLlvm.b.CreateStreamWriteStartOfFrame(dst)


class HlsStmWriteEndOfFrame(HlsWrite):
    """
    Statement which marks an end of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", hwIO:HwIO):
        super(HlsStmWriteEndOfFrame, self).__init__(parent, HVoidOrdering.from_py(None), hwIO, HVoidOrdering,
                                                    True,  # isVolatile
                                                    )

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        dst, _ = getArgumentForHwIO(toLlvm, self.dst, self._parent._ioProxyForIo[self.dst], self, False)
        dst: Argument
        return bb, toLlvm.b.CreateStreamWriteEndOfFrame(dst)
