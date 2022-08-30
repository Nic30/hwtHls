from typing import Optional, Union

from hwt.doc_markers import internal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.signalOps import SignalOps
from hwt.interfaces.std import Handshaked, Signal, VldSynced
from hwt.interfaces.structIntf import StructIntf
from hwt.interfaces.unionIntf import UnionSink, UnionSource
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.mainBases import InterfaceBase
from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.utils import _getNativeInterfaceWordType
from hwtHls.llvm.llvmIr import Register, MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeReadIndexed
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwtHls.ssa.value import SsaValue
from hwtLib.amba.axi_intf_common import Axi_hs

ANY_HLS_STREAM_INTF_TYPE = Union[Handshaked, Axi_hs, VldSynced,
                                 HsStructIntf, RtlSignal, Signal,
                                 UnionSink, UnionSource]


class HlsRead(HdlStatement, SignalOps, InterfaceBase, SsaInstr):
    """
    Container of informations about read from some stream
    """

    def __init__(self,
                 parent: "HlsScope",
                 src: ANY_HLS_STREAM_INTF_TYPE,
                 dtype: HdlType,
                 intfName:Optional[str]=None):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self.block: Optional[SsaBasicBlock] = None
        
        if intfName is None:
            intfName = getSignalName(src)
        var = parent.var
        name = f"{intfName:s}_read"
        sig = var(name, dtype)
        if isinstance(sig, Interface):
            w = dtype.bit_length()
            force_vector = False
            if w == 1 and isinstance(dtype, Bits):
                force_vector = dtype.force_vector
                
            sig_flat = var(name, Bits(w, force_vector=force_vector))
            # use flat signal and make type member fields out of slices of that signal
            sig = sig_flat._reinterpret_cast(dtype)
            sig._name = name
            sig_flat.drivers.append(self)
            sig_flat.origin = self
    
        else:
            sig_flat = sig
            sig.drivers.append(self)
            sig.origin = self

        self._sig = sig_flat
        self._GEN_NAME_PREFIX = intfName
        SsaInstr.__init__(self, parent.ssaCtx, sig_flat._dtype, OP_ASSIGN, (),
                          origin=sig)
        self._dtypeOrig = dtype
        if isinstance(sig, StructIntf):
            self._interfaces = sig._interfaces
            # copy all members on this object
            for field_path, field_intf in sig._fieldsToInterfaces.items():
                if len(field_path) == 1:
                    n = field_path[0]
                    assert not hasattr(self, n), (self, n)
                    assert not hasattr(self, n), ("name collision of ", self.__class__.__name__, "and read type member", n)
                    setattr(self, n, field_intf)
        else:
            self._interfaces = []

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def _getNativeInterfaceWordType(self) -> HdlType:
        return _getNativeInterfaceWordType(self._src)

    @classmethod
    def _translateMirToNetlist(cls,
                               representativeReadStm: "HlsRead",
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockSyncContainer,
                               instr: MachineInstr,
                               srcIo: Interface,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: HlsNetNodeOutAny,
                               instrDstReg: Register):
        """
        This method is called to generated HlsNetlist nodes from LLVM MIR.
        The purpose of this function is to make this translation customizable for specific :class:`hwt.synthesizer.interface.Interface` instances.
        
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
        valCache: MirToHwtHlsNetlistOpCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, Interface), srcIo
        assert isinstance(index, int) and index == 0, (srcIo, index, "Because this read is not addressed there should not be any index")
        n = HlsNetNodeRead(netlist, srcIo)

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.inputs.append(n)
        valCache.add(mbSync.block, instrDstReg, n._outputs[0], True)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {getSignalName(self._src):s}, {t}>"


class HlsReadAddressed(HlsRead):

    def __init__(self,
            parent:"HlsScope",
            src:Interface, index: Union[RtlSignal, HValue, Signal, SsaValue], element_t: HdlType):
        super(HlsReadAddressed, self).__init__(parent, src, element_t)
        self.operands = (index,)
        if isinstance(index, SsaValue):
            # assert index.block is not None, (index, "Must not construct instruction with operands which are not in SSA")
            index.users.append(self)

    @classmethod
    def _translateMirToNetlist(cls, mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockSyncContainer,
                               instr: MachineInstr,
                               srcIo: Interface,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: HlsNetNodeOutAny,
                               instrDstReg: Register):
        """
        :see: :meth:`~.HlsRead._translateMirToNetlist`
        """
        valCache: MirToHwtHlsNetlistOpCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, Interface), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constatnt it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeReadIndexed(netlist, srcIo)
        link_hls_nodes(index, n.indexes[0])

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.inputs.append(n)
        valCache.add(mbSync.block, instrDstReg, n._outputs[0], True)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {getSignalName(self._src):s}[{self.operands[0]}], {t}>"


class HlsStmReadStartOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to start of frame state.

    :attention: This does not read SOF flag from interface. (To get EOF you have to read data which contains also SOF flag.)
    """

    def __init__(self,
            parent:"HlsScope",
            src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, BIT)


class HlsStmReadEndOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to end of frame state.

    :attention: Does not read EOF flag from interface. (To get SOF you have to read data which contains also EOF flag.)
    """

    def __init__(self,
            parent:"HlsScope",
            src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, BIT)
