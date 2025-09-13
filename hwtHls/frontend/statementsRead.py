from typing import Optional, Union, Tuple, Sequence

from hwt.doc_markers import internal
from hwt.hObjList import HObjList
from hwt.hdl.commonConstants import b1
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct, HStructField
from hwt.hwIO import HwIO
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ioUtils import  \
    ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.llvm.llvmIr import Argument, ArrayType, TypeToArrayType, \
    Type, BasicBlock
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid, HVoidOrdering
from hwtHls.ssa.translation.toLlvmArgumentUtils import getArgumentForHwIO


def _copySliceNamesToFlattenedSignal(flatSig: HBitsRtlSignal, t: HdlType, name: str, offset:int):
    if isinstance(t, HStruct):
        for f in t.fields:
            f: HStructField
            w = f.dtype.bit_length()
            fTy = f.dtype
            if f.name is None:
                offset += fTy.bit_length()
            else:
                newName = f"{name:s}_{f.name:s}"
                offset = _copySliceNamesToFlattenedSignal(flatSig, fTy, newName, offset)

    elif isinstance(t, HArray):
        elmTy = t.element_t
        for i in range(t.size):
            newName = f"{name:s}_{i:d}"
            offset = _copySliceNamesToFlattenedSignal(flatSig, elmTy, newName, offset)
    else:
        w = t.bit_length()
        cur = flatSig[offset + w: offset]
        if cur._hasGenericName:
            cur._hasGenericName = False
            cur._name = name
        if w == 1:
            cur = flatSig[offset]
            if cur._hasGenericName:
                cur._hasGenericName = False
                cur._name = name
        offset += w

    return offset


class HlsRead(HdlStatement):
    """
    Container of informations about read from some IO.
    This object behaves as a HdlStatement and SsaInstr instance.
    By inheriting from all base classes it is possible to use this object in user code
    and to keep this object until conversion to LLVM.
    """

    def __init__(self,
                 parent: "HlsScope",
                 src: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType,
                 isBlocking: bool,
                 isVolatile: bool,
                 hwIOName: Optional[str]=None):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self._isBlocking = isBlocking
        self._isVolatile = isVolatile
        self.block: Optional[BasicBlock] = None

        if hwIOName is None:
            hwIOName = self._getInterfaceName(src)
        if hwIOName is None:
            name = "read"
        else:
            name = f"{hwIOName:s}_read"

        # create an interface and signals which will hold value of this object
        var = parent.var
        self._name = name
        isVoid = HdlType_isVoid(dtype)
        if isVoid:
            sig = None
        else:
            sig = var(name, dtype, arrayPartitionComplete=isinstance(dtype, HArray))

        if isVoid:
            w = 0
            if isBlocking:
                sig_flat = None
            else:
                sig_flat = var(name, HBits(1, force_vector=True))
                sig_flat._rtlDrivers.append(self)
                sig_flat._rtlObjectOrigin = self

        elif isinstance(sig, (HwIO, tuple, HObjList)) or not isBlocking:
            w = dtype.bit_length()
            force_vector = False
            totalWidth = w + (0 if isBlocking else 1)
            if totalWidth == 1 and isinstance(dtype, HBits):
                force_vector = dtype.force_vector

            sig_flat = var(name, HBits(totalWidth, force_vector=force_vector))
            # use flat signal and make type member fields out of slices of that signal
            if isBlocking:
                sig = sig_flat._reinterpret_cast(dtype)
            else:
                sig = sig_flat[w:]._reinterpret_cast(dtype)
            sig._name = name
            sig_flat._rtlDrivers.append(self)
            sig_flat._rtlObjectOrigin = self
            _copySliceNamesToFlattenedSignal(sig_flat, dtype, name, 0)
        else:
            sig_flat = sig
            sig._rtlDrivers.append(self)
            sig._rtlObjectOrigin = self

        self._sig = sig_flat
        self._GEN_NAME_PREFIX = hwIOName
        self._dtype = sig_flat._dtype if sig_flat is not None else dtype
        self._dtypeOrig = dtype
        self.data = sig
        if isBlocking:
            self.valid = b1
        else:
            self.valid = sig_flat[w]

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def _translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", bb: BasicBlock):
        src, elmT = getArgumentForHwIO(toLlvm, self._src, self._parent._ioProxyForIo[self._src], self, True)
        src: Argument
        elmT: Type
        # [todo] see mustSuppressSpeculation
        v = toLlvm.b.CreateLoad(elmT, src, self._isVolatile, toLlvm.strCtx.addTwine(self._name))
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HwIO_getName(self._parent.parentHwModule, io)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name", None)
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._getInterfaceName(self._src):s}, {t}>"


class HlsReadAddressed(HlsRead):
    """
    Variant of :class:`~.HlsRead` with an index or address input.
    """

    def __init__(self, parent:"HlsScope",
                 src:HwIO,
                 index: ANY_SCALAR_INT_VALUE,
                 element_t: HdlType,
                 isBlocking:bool,
                 isVolatile:bool,
                 hwIOName: Optional[str]=None):
        super(HlsReadAddressed, self).__init__(parent, src, element_t, isBlocking, isVolatile, hwIOName=hwIOName)
        self.index = index

    @override
    def _translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", bb: BasicBlock):
        src, t = getArgumentForHwIO(toLlvm, self._src, self._parent._ioProxyForIo[self._src], self, True)
        src: Argument
        t: Type
        # :note: the index type does not matter much as llvm::InstCombine extends it to i64
        index_t = Type.getIntNTy(toLlvm.ctx, 64)
        indexes = [toLlvm._translateExprInt(0, index_t)]
        bb, index0 = toLlvm._translateExprToLlvm(bb, self.index)
        index0 = toLlvm.b.CreateZExt(index0, index_t)
        indexes.append(index0)
        arrTy: ArrayType = TypeToArrayType(t)
        assert arrTy is not None, ("It is expected that this object access data of array type", self, t)
        elmT = arrTy.getElementType()
        ptr = toLlvm.b.CreateInBoundsGEP(arrTy, src, indexes)
        name = toLlvm.strCtx.addTwine(self._name)
        v = toLlvm.b.CreateLoad(elmT, ptr, self._isVolatile, name)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._getInterfaceName(self._src):s}[{self.index}], {t}>"


class HlsStmReadStartOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to start of frame state.

    :attention: This does not read SOF flag from interface. (To get EOF you have to read data which contains also SOF flag.)
    """

    def __init__(self, parent:"HlsScope", src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, HVoidOrdering, True, isVolatile=True)

    @override
    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        src, _ = getArgumentForHwIO(toLlvm, self._src, self._parent._ioProxyForIo[self._src], self, True)
        src: Argument
        v = toLlvm.b.CreateStreamReadStartOfFrame(src)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)


class HlsStmReadEndOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to end of frame state.

    :attention: Does not read EOF flag from interface. (To get SOF you have to read data which contains also EOF flag.)
    """

    def __init__(self, parent:"HlsScope", src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, HVoidOrdering, True, isVolatile=True)

    @override
    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator", bb: BasicBlock):
        src, _ = getArgumentForHwIO(toLlvm, self._src, self._parent._ioProxyForIo[self._src], self, True)
        src: Argument
        v = toLlvm.b.CreateStreamReadEndOfFrame(src)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)
