from typing import Optional, Union, Tuple, Sequence

from hwt.doc_markers import internal
from hwt.hdl.commonConstants import b1
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.struct import HStruct, HStructField
from hwt.hwIO import HwIO
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ioUtils import _getNativeInterfaceWordType, \
    ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.frontend.utils import HwIO_getName
from hwtHls.io.portGroups import getFirstInterfaceInstance, MultiPortGroup, \
    BankedPortGroup
from hwtHls.llvm.llvmIr import Register, MachineInstr, Argument, ArrayType, TypeToArrayType, \
    Type, BasicBlock
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid, HVoidOrdering
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readIndexed import HlsNetNodeReadIndexed
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
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

        # create an interface and signals which will hold value of this object
        var = parent._sig  # can not use .var() because it would prematurely create tmp alloca for result
        name = f"{hwIOName:s}_read"
        self._name = name
        isVoid = HdlType_isVoid(dtype)
        if isVoid:
            sig = None
        else:
            sig = var(name, dtype)

        if isVoid:
            w = 0
            if isBlocking:
                sig_flat = None
            else:
                sig_flat = var(name, HBits(1, force_vector=True))
                sig_flat._rtlDrivers.append(self)
                sig_flat._rtlObjectOrigin = self

        elif isinstance(sig, HwIO) or not isBlocking:
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

    def _getNativeInterfaceWordType(self) -> HdlType:
        return _getNativeInterfaceWordType(getFirstInterfaceInstance(self._src))

    def _translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", bb: BasicBlock):
        src, elmT = getArgumentForHwIO(toLlvm, self._src, self, True)
        src: Argument
        elmT: Type
        # [todo] see mustSuppressSpeculation
        v = toLlvm.b.CreateLoad(elmT, src, self._isVolatile, toLlvm.strCtx.addTwine(self._name))
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)

    @classmethod
    def _translateMirToNetlist(cls,
                               representativeReadStm: "HlsRead",
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: Union[HwIO, RtlSignalBase],
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        """
        This method is called to generated HlsNetlist nodes from LLVM MIR.
        The purpose of this function is to make this translation customizable for specific :class:`hwt.hwIO.HwIO` instances.

        :param representativeReadStm: Any found read for this interface before LLVM opt.
            We can not find the original because optimization process may remove and generate new reads and exact mapping can not be found.
            This may be used to find meta informations about interface.
        :param mirToNetlist: Main object form LLVM MIR to HlsNetlist translation.
        :param instr: LLVM MIR instruction which is being translated
        :param srcIo: An interface used by this instruction.
        :param index: An index to specify the address used in this read.
        :param cond: An enable condition for this operation to happen.
        :param instrDstReg: A register where this instruction stores the read data.
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, (HwIO, RtlSignalBase, MultiPortGroup, BankedPortGroup)), srcIo
        assert isinstance(index, int) and index == 0, (srcIo, index, "Because this read is not addressed there should not be any index")
        assert representativeReadStm._src is srcIo, (representativeReadStm, srcIo)

        dtype = representativeReadStm._getNativeInterfaceWordType()
        expectedWidth = mirToNetlist.mf.getRegInfo().getType(instrDstReg).getScalarSizeInBits()
        if not representativeReadStm._isBlocking:
            assert expectedWidth == dtype.bit_length() + 1, ("Width of physical signals of IO must be what is expected from LLVM MIR", instrDstReg, expectedWidth, dtype)
        else:
            assert expectedWidth == dtype.bit_length(), ("Width of physical signals of IO must be what is expected from LLVM MIR", instrDstReg, expectedWidth, dtype)

        if (isinstance(dtype, HBits) and dtype.signed is not None) or not dtype.isScalar():
            dtype = HBits(dtype.bit_length())

        n = HlsNetNodeRead(netlist,
                           srcIo,
                           dtype=dtype,
                           name=f"ld_r{instr.getOperand(0).getReg().virtRegIndex():d}")
        mbMeta.parentElement.addNode(n)
        if not representativeReadStm._isBlocking:
            n.setNonBlocking()

        mirToNetlist._addExtraCond(n, cond, mbMeta.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbMeta.blockEn)
        mbMeta.addOrderedNode(n)
        if representativeReadStm._isBlocking:
            o = n._portDataOut
        else:
            o = n.getRawValue()
        assert not isinstance(o._dtype, HBits) or not o._dtype.signed, (
            "At this stage all values of HBits type should have signed=None", o)  # can potentially be of void type
        valCache.add(mbMeta.block, instrDstReg, o, True)

        return [n, ]

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
        src, t = getArgumentForHwIO(toLlvm, self._src, self, True)
        src: Argument
        t: Type
        # :note: the index type does not matter much as llvm::InstCombine extends it to i64
        index_t = Type.getIntNTy(toLlvm.ctx, self.index._dtype.bit_length())
        indexes = [toLlvm._translateExprInt(0, index_t)]
        bb, index0 = toLlvm._translateExprToLlvm(bb, self.index)
        indexes.append(index0)
        arrTy: ArrayType = TypeToArrayType(t)
        assert arrTy is not None, ("It is expected that this object access data of array type", self, t)
        elmT = arrTy.getElementType()
        ptr = toLlvm.b.CreateGEP(arrTy, src, indexes)
        name = toLlvm.strCtx.addTwine(self._name)
        v = toLlvm.b.CreateLoad(elmT, ptr, self._isVolatile, name)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)

    @classmethod
    def _translateMirToNetlist(cls,
                               representativeReadStm: "HlsReadAddresed",
                               mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbMeta: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: HwIO,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Optional[HlsNetNodeOutAny],
                               instrDstReg: Register) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`~.HlsRead._translateMirToNetlist`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, HwIO), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeReadIndexed(netlist, srcIo, name=f"ld_r{instr.getOperand(0).getReg().virtRegIndex()}")
        index.connectHlsIn(n.indexes[0])
        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)
        o = n._portDataOut
        assert isinstance(o._dtype, HBits)
        sign = o._dtype.signed
        if sign is None:
            pass
        elif sign:
            raise NotImplementedError()
        else:
            raise NotImplementedError()
        valCache.add(mbMeta.block, instrDstReg, o, True)

        return [n, ]

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
        src, _ = getArgumentForHwIO(toLlvm, self._src, self, True)
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
        src, _ = getArgumentForHwIO(toLlvm, self._src, self, True)
        src: Argument
        v = toLlvm.b.CreateStreamReadEndOfFrame(src)
        return toLlvm._translateToLlvm_HlsRead_registerVar(bb, self, v)
