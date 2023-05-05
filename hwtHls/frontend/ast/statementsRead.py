from typing import Optional, Union, Tuple

from hwt.doc_markers import internal
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.synthesizer.interface import Interface
from hwtHls.frontend.ast.utils import _getNativeInterfaceWordType, \
    ANY_HLS_STREAM_INTF_TYPE, ANY_SCALAR_INT_VALUE
from hwtHls.frontend.utils import getInterfaceName
from hwtHls.llvm.llvmIr import Register, MachineInstr
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOutAny, link_hls_nodes, \
    HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead, HlsNetNodeReadIndexed
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr, OP_ASSIGN
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.value import SsaValue


class HlsRead(HdlStatement, SsaInstr):
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
                 intfName: Optional[str]=None):
        super(HlsRead, self).__init__()
        self._isAccessible = True
        self._parent = parent
        self._src = src
        self._isBlocking = isBlocking
        self.block: Optional[SsaBasicBlock] = None

        if intfName is None:
            intfName = self._getInterfaceName(src)

        # create an interface and signals which will hold value of this object
        var = parent.var
        name = f"{intfName:s}_read"
        sig = var(name, dtype)
        if isinstance(sig, Interface) or not isBlocking:
            w = dtype.bit_length()
            force_vector = False
            if w == 1 and isinstance(dtype, Bits):
                force_vector = dtype.force_vector

            sig_flat = var(name, Bits(w + (0 if isBlocking else 1), force_vector=force_vector))
            # use flat signal and make type member fields out of slices of that signal
            if isBlocking:
                sig = sig_flat._reinterpret_cast(dtype)
            else:
                sig = sig_flat[w:]._reinterpret_cast(dtype)
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
        self.data = sig
        if isBlocking:
            self.valid = BIT.from_py(1)
        else:
            self.valid = sig_flat[w]

    @internal
    def _get_rtl_context(self) -> 'RtlNetlist':
        return self._parent.ctx

    def _getNativeInterfaceWordType(self) -> HdlType:
        return _getNativeInterfaceWordType(self._src)

    @classmethod
    def _outAsBitVec(cls, netlist: HlsNetlistCtx,
                     mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                     o: HlsNetNodeOut,
                     name: Optional[str]) -> HlsNetNodeOut:
        assert isinstance(o._dtype, Bits)
        sign = o._dtype.signed
        if sign is None:
            pass
        else:
            toBits = HlsNetNodeOperator(netlist, AllOps.BitsAsVec, 1, Bits(o._dtype.bit_length()), name)
            mirToNetlist.nodes.append(toBits)
            link_hls_nodes(o, toBits._inputs[0])
            o = toBits._outputs[0]
        return o

    @classmethod
    def _translateMirToNetlist(cls,
                               representativeReadStm: "HlsRead",
                               mirToNetlist:"HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: Interface,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Union[int, HlsNetNodeOutAny],
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
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, Interface), srcIo
        assert isinstance(index, int) and index == 0, (srcIo, index, "Because this read is not addressed there should not be any index")
        n = HlsNetNodeRead(netlist, srcIo)
        if not representativeReadStm._isBlocking:
            n.setNonBlocking()

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.inputs.append(n)

        o = n._outputs[0] if representativeReadStm._isBlocking else n._rawValue
        o = cls._outAsBitVec(netlist, mirToNetlist, o, n.name)
        valCache.add(mbSync.block, instrDstReg, o, True)

    def _getInterfaceName(self, io: Union[Interface, Tuple[Interface]]) -> str:
        return getInterfaceName(self._parent.parentUnit, io)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._getInterfaceName(self._src):s}, {t}>"


class HlsReadAddressed(HlsRead):
    """
    Variant of :class:`~.HlsRead` with an index or address input.
    """

    def __init__(self, parent:"HlsScope",
                 src:Interface,
                 index: ANY_SCALAR_INT_VALUE,
                 element_t: HdlType,
                 isBlocking:bool,
                 intfName: Optional[str]=None):
        super(HlsReadAddressed, self).__init__(parent, src, element_t, isBlocking, intfName=intfName)
        self.operands = (index,)
        if isinstance(index, SsaValue):
            # assert index.block is not None, (index, "Must not construct instruction with operands which are not in SSA")
            index.users.append(self)

    @classmethod
    def _translateMirToNetlist(cls, mirToNetlist: "HlsNetlistAnalysisPassMirToNetlist",
                               mbSync: MachineBasicBlockMeta,
                               instr: MachineInstr,
                               srcIo: Interface,
                               index: Union[int, HlsNetNodeOutAny],
                               cond: Union[int, HlsNetNodeOutAny],
                               instrDstReg: Register):
        """
        :see: :meth:`~.HlsRead._translateMirToNetlist`
        """
        valCache: MirToHwtHlsNetlistValueCache = mirToNetlist.valCache
        netlist: HlsNetlistCtx = mirToNetlist.netlist
        assert isinstance(srcIo, Interface), srcIo
        if isinstance(index, int):
            raise AssertionError("If the index is constant it should be an output of a constant node but it is an integer", srcIo, instr)

        n = HlsNetNodeReadIndexed(netlist, srcIo)
        link_hls_nodes(index, n.indexes[0])

        mirToNetlist._addExtraCond(n, cond, mbSync.blockEn)
        mirToNetlist._addSkipWhen_n(n, cond, mbSync.blockEn)
        mbSync.addOrderedNode(n)
        mirToNetlist.inputs.append(n)
        o = n._outputs[0]
        assert isinstance(o._dtype, Bits)
        sign = o._dtype.signed
        if sign is None:
            pass
        elif sign:
            raise NotImplementedError()
        else:
            raise NotImplementedError()
        valCache.add(mbSync.block, instrDstReg, o, True)

    def __repr__(self):
        t = self._dtype
        tName = getattr(t, "name")
        if tName is not None:
            t = tName

        return f"<{self.__class__.__name__} {self._name:s} {self._getInterfaceName(self._src):s}[{self.operands[0]}], {t}>"


class HlsStmReadStartOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to start of frame state.

    :attention: This does not read SOF flag from interface. (To get EOF you have to read data which contains also SOF flag.)
    """

    def __init__(self,
            parent:"HlsScope",
            src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, BIT, True)


class HlsStmReadEndOfFrame(HlsRead):
    """
    A statement which switches the reader FSM to end of frame state.

    :attention: Does not read EOF flag from interface. (To get SOF you have to read data which contains also EOF flag.)
    """

    def __init__(self,
            parent:"HlsScope",
            src:ANY_HLS_STREAM_INTF_TYPE):
        HlsRead.__init__(self, parent, src, BIT, True)
