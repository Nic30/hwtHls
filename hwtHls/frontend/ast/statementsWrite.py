from typing import Union, Tuple, Sequence, Optional

from hwt.hdl.const import HConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.synthesizer.interfaceLevel.hwModuleImplHelpers import HwIO_getName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statements import HlsStm
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.utils import _getNativeInterfaceWordType, \
    ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.llvm.llvmIr import MachineInstr, Argument, Type, ArrayType, TypeToArrayType
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.writeIndexed import HlsNetNodeWriteIndexed
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.value import SsaValue


class HlsWrite(HlsStm, SsaInstr):
    """
    Container of informations about write in some stream
    """

    def __init__(self,
                 parent: "HlsScope",
                 src:Union[SsaValue, HConst],
                 dst: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType,
                 mayBecomeFlushable=True,
                 ):
        HlsStm.__init__(self, parent)
        if isinstance(dst, RtlSignal):
            hwIO, indexes, sign_cast_seen = dst._getIndexCascade()
            if hwIO is not dst or indexes:
                raise AssertionError("Use :class:`~.HlsWriteAddressed` if you require addressing", hwIO, indexes, sign_cast_seen)
        else:
            assert not isinstance(dst, (int, HConst)), dst
        SsaInstr.__init__(self, parent.ssaCtx, dtype, OP_ASSIGN, ())
        # [todo] this put this object in temporary inconsistent state,
        #  because src can be more than just SsaValue/HConst instance
        self.operands = (src,)
        if isinstance(src, SsaValue):
            # assert src.block is not None, (src, "Must not construct instruction with operands which are not in SSA")
            src.users.append(self)
        self._parent = parent

        # store original source for debugging
        self._origSrc = src
        self.dst = dst
        self.mayBecomeFlushable = mayBecomeFlushable

    def getSrc(self):
        assert len(self.operands) == 1, self
        return self.operands[0]

    def _getNativeInterfaceWordType(self) -> HdlType:
        return _getNativeInterfaceWordType(self.dst)

    def _getInterfaceName(self, io: Union[HwIO, Tuple[HwIO]]) -> str:
        return HlsRead._getInterfaceName(self, io)

    def _translateToLlvm(self, toLlvm: 'ToLlvmIrTranslator'):
        b = toLlvm.b
        dst, _, t = toLlvm.ioToVar[self.dst]
        dst: Argument
        t: Type
        src = toLlvm._translateExpr(self.getSrc())
        return b.CreateStore(src, dst, True)

    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Union[HwIO, RtlSignal],
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, (HwIO, RtlSignal)), dstIo
        assert isinstance(index, int) and index == 0, (instr, index, "Because this read is not addressed there should not be any index")
        n = HlsNetNodeWrite(netlist, dstIo, mayBecomeFlushable=representativeWriteStm.mayBecomeFlushable)
        mbMeta.parentElement.addNode(n)
        srcVal.connectHlsIn(n._inputs[0])

        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.addOrderedNode(n)
        return [n, ]

    def __repr__(self):
        src = self.operands[0]
        return f"<{self.__class__.__name__} {src if isinstance(src, HConst) else src._name}->{HwIO_getName(self._parent.parentHwModule, self.dst)}>"


class HlsWriteAddressed(HlsWrite):

    def __init__(self,
            parent:"HlsScope",
            src:Union[SsaValue, HConst],
            dst:HwIO,
            index: ANY_SCALAR_INT_VALUE,
            element_t: HdlType,
            mayBecomeFlushable=True):
        HlsWrite.__init__(self, parent, src, dst, element_t, mayBecomeFlushable=mayBecomeFlushable)
        self.operands = (src, index)
        if isinstance(index, SsaValue):
            # assert index.block is not None, (index, "Must not construct instruction with operands which are not in SSA")
            index.users.append(self)
        # store original index for debugging
        self._origIndex = index

    def getSrc(self):
        assert len(self.operands) == 2, self
        return self.operands[0]

    def getIndex(self):
        assert len(self.operands) == 2, self
        return self.operands[1]

    def _translateToLlvm(self, toLlvm: 'ToLlvmIrTranslator'):
        b = toLlvm.b
        dst, _, t = toLlvm.ioToVar[self.dst]
        dst: Argument
        t: Type
        src = toLlvm._translateExpr(self.getSrc())
        # :note: the index type does not matter much as llvm::InstCombine extends it to i64
        index_t = Type.getIntNTy(toLlvm.ctx, self.getIndex()._dtype.bit_length())
        indexes = [toLlvm._translateExprInt(0, index_t),
                                             toLlvm._translateExpr(self.getIndex()), ]
        arrTy: ArrayType = TypeToArrayType(t)
        # elmT = arrTy.getElementType()
        dst = b.CreateGEP(arrTy, dst, indexes)

        return b.CreateStore(src, dst, True)

    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            mbMeta: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: HwIO,
            index: Union[int, HlsNetNodeOutAny],
            cond: Optional[HlsNetNodeOutAny],) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, HwIO), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
        n = HlsNetNodeWriteIndexed(netlist, dstIo, mayBecomeFlushable=representativeWriteStm.mayBecomeFlushable)
        index.connectHlsIn(n.indexes[0])
        srcVal.connectHlsIn(n._inputs[0])

        _cond = cond
        # _cond = mbMeta.syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, None)
        mirToNetlist._addSkipWhen_n(n, _cond, None)
        mbMeta.parentElement.addNode(n)
        mbMeta.addOrderedNode(n)
        return [n, ]

    def __repr__(self):
        src, index = self.operands
        if isinstance(src, (HwIO, RtlSignal)):
            src = HwIO_getName(self._parent.parentHwModule, src)
        if isinstance(index, (HwIO, RtlSignal)):
            index = HwIO_getName(self._parent.parentHwModule, index)

        return f"<{self.__class__.__name__} {src}->{HwIO_getName(self._parent.parentHwModule, self.dst)}[{index}]>"


class HlsStmWriteStartOfFrame(HlsWrite):
    """
    Statement which marks a start of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", hwIO:HwIO):
        super(HlsStmWriteStartOfFrame, self).__init__(parent, BIT.from_py(1), hwIO, BIT)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        return toLlvm.b.CreateStreamWriteStartOfFrame(dst)


class HlsStmWriteEndOfFrame(HlsWrite):
    """
    Statement which marks an end of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", hwIO:HwIO):
        super(HlsStmWriteEndOfFrame, self).__init__(parent, BIT.from_py(1), hwIO, BIT)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        return toLlvm.b.CreateStreamWriteEndOfFrame(dst)
