from typing import Union, Tuple, Sequence

from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getInterfaceName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.statements import HlsStm
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.utils import _getNativeInterfaceWordType, \
    ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.llvm.llvmIr import MachineInstr, Argument, Type, ArrayType, TypeToArrayType
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes
from hwtHls.netlist.nodes.write import HlsNetNodeWrite, HlsNetNodeWriteIndexed
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.value import SsaValue
from hwtLib.types.ctypes import uint64_t


class HlsWrite(HlsStm, SsaInstr):
    """
    Container of informations about write in some stream
    """

    def __init__(self,
                 parent: "HlsScope",
                 src:Union[SsaValue, HValue],
                 dst: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType):
        HlsStm.__init__(self, parent)
        if isinstance(dst, RtlSignal):
            intf, indexes, sign_cast_seen = dst._getIndexCascade()
            if intf is not dst or indexes:
                raise AssertionError("Use :class:`~.HlsWriteAddressed` if you require addressing", intf, indexes, sign_cast_seen)
        else:
            assert not isinstance(dst, (int, HValue)), dst
        SsaInstr.__init__(self, parent.ssaCtx, dtype, OP_ASSIGN, ())
        # [todo] this put this object in temporary inconsistent state,
        #  because src can be more than just SsaValue/HValue instance
        self.operands = (src,)
        if isinstance(src, SsaValue):
            # assert src.block is not None, (src, "Must not construct instruction with operands which are not in SSA")
            src.users.append(self)
        self._parent = parent

        # store original source for debugging
        self._origSrc = src
        self.dst = dst

    def getSrc(self):
        assert len(self.operands) == 1, self
        return self.operands[0]

    def _getNativeInterfaceWordType(self) -> HdlType:
        return _getNativeInterfaceWordType(self.dst)

    def _getInterfaceName(self, io: Union[Interface, Tuple[Interface]]) -> str:
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
            syncTracker: InsideOfBlockSyncTracker,
            mbSync: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Union[Interface, RtlSignal],
            index: Union[int, HlsNetNodeOutAny],
            cond: Union[int, HlsNetNodeOutAny]) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, (Interface, RtlSignal)), dstIo
        assert isinstance(index, int) and index == 0, (instr, index, "Because this read is not addressed there should not be any index")
        n = HlsNetNodeWrite(netlist, dstIo)
        link_hls_nodes(srcVal, n._inputs[0])

        _cond = syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, _cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)
        return [n, ]

    def __repr__(self):
        src = self.operands[0]
        return f"<{self.__class__.__name__} {src if isinstance(src, HValue) else src._name}->{getInterfaceName(self._parent.parentUnit, self.dst)}>"


class HlsWriteAddressed(HlsWrite):

    def __init__(self,
            parent:"HlsScope",
            src:Union[SsaValue, HValue],
            dst:Interface,
            index: ANY_SCALAR_INT_VALUE,
            element_t: HdlType):
        HlsWrite.__init__(self, parent, src, dst, element_t)
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
        indexes = [toLlvm._translateExprInt(0, toLlvm._translateType(uint64_t)),
                                             toLlvm._translateExpr(self.getIndex()), ]
        arrTy: ArrayType = TypeToArrayType(t)
        # elmT = arrTy.getElementType()
        dst = b.CreateGEP(arrTy, dst, indexes)

        return b.CreateStore(src, dst, True)

    @classmethod
    def _translateMirToNetlist(cls,
            representativeWriteStm: "HlsWrite",
            mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
            syncTracker: InsideOfBlockSyncTracker,
            mbSync: MachineBasicBlockMeta,
            instr: MachineInstr,
            srcVal: HlsNetNodeOutAny,
            dstIo: Interface,
            index: Union[int, HlsNetNodeOutAny],
            cond: Union[int, HlsNetNodeOutAny]) -> Sequence[HlsNetNode]:
        """
        :see: :meth:`hwtHls.frontend.ast.statementsRead.HlsRead._translateMirToNetlist`
        """
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        # srcVal, dstIo, index, cond = ops
        assert isinstance(dstIo, Interface), dstIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", dstIo, instr)
        n = HlsNetNodeWriteIndexed(netlist, dstIo)
        link_hls_nodes(index, n.indexes[0])
        link_hls_nodes(srcVal, n._inputs[0])

        _cond = syncTracker.resolveControlOutput(cond)
        mirToNetlist._addExtraCond(n, _cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, _cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.outputs.append(n)
        return [n, ]

    def __repr__(self):
        src, index = self.operands
        if isinstance(src, (Interface, RtlSignal)):
            src = getInterfaceName(self._parent.parentUnit, src)
        if isinstance(index, (Interface, RtlSignal)):
            index = getInterfaceName(self._parent.parentUnit, index)

        return f"<{self.__class__.__name__} {src}->{getInterfaceName(self._parent.parentUnit, self.dst)}[{index}]>"


class HlsStmWriteStartOfFrame(HlsWrite):
    """
    Statement which marks a start of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", intf:Interface):
        super(HlsStmWriteStartOfFrame, self).__init__(parent, BIT.from_py(1), intf, BIT)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        return toLlvm.b.CreateStreamWriteStartOfFrame(dst)


class HlsStmWriteEndOfFrame(HlsWrite):
    """
    Statement which marks an end of frame on specified interface.
    """

    def __init__(self, parent:"HlsScope", intf:Interface):
        super(HlsStmWriteEndOfFrame, self).__init__(parent, BIT.from_py(1), intf, BIT)

    def _translateToLlvm(self, toLlvm:"ToLlvmIrTranslator"):
        dst, _, _ = toLlvm.ioToVar[self.dst]
        dst: Argument
        return toLlvm.b.CreateStreamWriteEndOfFrame(dst)
