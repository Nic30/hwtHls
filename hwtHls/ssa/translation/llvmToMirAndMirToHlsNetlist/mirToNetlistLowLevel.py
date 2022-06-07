from typing import Set, Tuple, Dict, List, Union, Type

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.unit import Unit
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, \
    TargetOpcode, CmpInst, ConstantInt, TypeToIntegerType, IntegerType, Type as LlvmType, \
    MachineLoopInfo
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    link_hls_nodes, HlsNetNodeOutAny
from hwtHls.netlist.utils import hls_op_and
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class HlsNetlistAnalysisPassMirToNetlistLowLevel(HlsNetlistAnalysisPass):
    """
    This object translates low level elements of LLVM MIR to hwtHls HlsNetlist
    """
    OPC_TO_OP = {
        TargetOpcode.G_ADD: AllOps.ADD,
        TargetOpcode.G_SUB: AllOps.SUB,
        TargetOpcode.G_MUL: AllOps.MUL,
        TargetOpcode.G_AND: AllOps.AND,
        TargetOpcode.G_OR: AllOps.OR,
        TargetOpcode.G_XOR: AllOps.XOR,
        TargetOpcode.GENFPGA_NOT: AllOps.NOT,
    }
    SIGNED_CMP_OPS = (
        CmpInst.Predicate.ICMP_SGT,
        CmpInst.Predicate.ICMP_SGE,
        CmpInst.Predicate.ICMP_SLT,
        CmpInst.Predicate.ICMP_SLE,
    )
    CMP_PREDICATE_TO_OP = {
        CmpInst.Predicate.ICMP_EQ:AllOps.EQ,
        CmpInst.Predicate.ICMP_NE:AllOps.NE,
        CmpInst.Predicate.ICMP_UGT:AllOps.GT,
        CmpInst.Predicate.ICMP_UGE:AllOps.GE,
        CmpInst.Predicate.ICMP_ULT:AllOps.LT,
        CmpInst.Predicate.ICMP_ULE:AllOps.LE,
        CmpInst.Predicate.ICMP_SGT:AllOps.GT,
        CmpInst.Predicate.ICMP_SGE:AllOps.GE,
        CmpInst.Predicate.ICMP_SLT:AllOps.LT,
        CmpInst.Predicate.ICMP_SLE:AllOps.LE,
    }

    def __init__(self, hls: "HlsStreamProc", tr: ToLlvmIrTranslator,
                 mf: MachineFunction,
                 backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                 liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                 ioRegs: List[Register],
                 registerTypes: Dict[Register, int],
                 loops: MachineLoopInfo
                 ):
        super(HlsNetlistAnalysisPassMirToNetlistLowLevel, self).__init__(HlsNetlistCtx(hls.parentUnit, hls.freq, tr.label))
        # :note: value of a block in block0 means that the control flow was passed to block0 from block 
        netlist = self.netlist
        self.valCache = MirToHwtHlsNetlistOpCache(netlist)
        aargToArgIndex = {a: i for (i, a) in enumerate(tr.llvm.main.args())}
        self._argIToIo = {aargToArgIndex[a]: io for (io, a) in tr.ioToVar.items()}
        self.blockSync: Dict[MachineBasicBlock, MachineBasicBlockSyncContainer] = {}
        self.nodes: List[HlsNetNode] = netlist.nodes
        self.inputs: List[HlsNetNodeRead] = netlist.inputs
        self.outputs: List[HlsNetNodeWrite] = netlist.outputs
        self.regToIo: Dict[Register, Interface] = {}
        self.mf = mf
        self.backedges = backedges
        self.liveness = liveness
        self.registerTypes = registerTypes
        self.regToIo = {ioRegs[ai]: io for (ai, io) in self._argIToIo.items()}
        self.loops = loops
        # register self in netlist analysis cache
        netlist._analysis_cache[self.__class__] = self

    def _constructBackedgeBuffer(self, name: str, srcBlock: MachineBasicBlock, dstBlock: MachineBasicBlock, cacheKey, val: HlsNetNodeOutAny) -> HlsNetNodeOut:
        # we need to insert backedge buffer to get block en flag from pred to mb
        srcName = srcBlock.getName().str()
        dstName = dstBlock.getName().str()
        _, r_from_in = self._add_hs_intf_and_read(
            f"{name:s}_{srcName:s}_to_{dstName:s}_out",
            val._dtype,
            HlsNetNodeReadBackwardEdge)
        self.valCache.add(dstBlock, cacheKey, r_from_in, False)
        
        _, w_to_out = self._add_hs_intf_and_write(f"{name:s}_{srcName:s}_to_{dstName:s}_in", val._dtype,
                                                  val, HlsNetNodeWriteBackwardEdge)
        w_to_out.associate_read(r_from_in.obj)
        return r_from_in
        
    def _translateType(self, t: LlvmType):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return Bits(it.getBitWidth())
        else:
            raise NotImplementedError(t)

    def _translateConstant(self, c: ConstantInt):
        val = int(c.getValue())
        t = self._translateType(c.getType())
        if not t.signed and val < 0:  # convert to unsigned
            val = t.all_mask() + val + 1
        v = t.from_py(val)
        n = HlsNetNodeConst(self.netlist, v)
        self.nodes.append(n)
        # mbSync.nodes.append(n)
        return n._outputs[0]

    def _translateIntBit(self, val: int):
        v = BIT.from_py(val)
        n = HlsNetNodeConst(self.netlist, v)
        self.nodes.append(n)
        # mbSync.nodes.append(n)
        return n._outputs[0]

    def _translateRegister(self, block: MachineBasicBlock, r: Register):
        io = self.regToIo.get(r, None)
        if io is not None:
            return io

        bw = self.registerTypes.get(r, None)
        if bw is None:
            return self.regToIo[r]

        res = self.valCache.get(block, r, Bits(bw))
        assert isinstance(res, (HlsNetNodeOut, HlsNetNodeOutLazy)), res
        return res

    def _translateMBB(self, block: MachineBasicBlock):
        return self.valCache.get(block, block, BIT)

    def _add_hs_intf_and_read(self,
                              suggested_name: str, dtype:HdlType,
                              read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead) -> Tuple[Interface, HlsNetNodeRead]:
        intf = HsStructIntf()
        intf.T = dtype
        return intf, self._add_intf_and_read(intf, suggested_name, read_cls=read_cls)

    def _add_hs_intf_and_write(self, suggested_name: str, dtype:HdlType,
                               val: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                               write_cls:Type[HlsNetNodeWrite]=HlsNetNodeWrite):
        intf = HsStructIntf()
        intf.T = dtype
        self._add_intf_instance(intf, suggested_name)
        return intf, self._write_to_io(intf, val, write_cls=write_cls)

    def _add_intf_and_read(self,
                           intf: Interface,
                           suggested_name: str,
                           read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead) -> Interface:
        self._add_intf_instance(intf, suggested_name)
        return self._read_from_io(intf, read_cls=read_cls)

    def _add_intf_instance(self, intf: Interface, suggested_name: str) -> Interface:
        """
        Spot interface instance in parent unit.
        """
        u:Unit = self.netlist.parentUnit
        return Interface_without_registration(u, intf, f"hls_{suggested_name:s}")

    def _read_from_io(self, intf: Interface, read_cls:Type[HlsNetNodeRead]=HlsNetNodeRead) -> HlsNetNodeOut:
        """
        Instantiate HlsNetNodeRead operation for this specific interface.
        """
        read: HlsNetNodeRead = read_cls(self.netlist, intf)
        self.inputs.append(read)
        return read._outputs[0]

    def _write_to_io(self, intf: Interface,
                     val: Union[HlsNetNodeOut, HlsNetNodeOutLazy],
                     write_cls:Type[HlsNetNodeWrite]=HlsNetNodeWrite) -> HlsNetNodeWrite:
        """
        Instantiate HlsNetNodeWrite operation for this specific interface.
        """
        write = write_cls(self.netlist, val, intf)
        link_hls_nodes(val, write._inputs[0])
        self.outputs.append(write)
        return write

    def _addExtraCond(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite], cond: Union[int, HlsNetNodeOutAny], blockEn: HlsNetNodeOutLazy):
        if isinstance(cond, int):
            assert cond == 1, cond
            cond = blockEn
        else:
            cond = hls_op_and(self.netlist, blockEn, cond)
        n.add_control_extraCond(cond)
