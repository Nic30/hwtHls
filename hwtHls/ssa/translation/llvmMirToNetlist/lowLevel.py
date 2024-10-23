from typing import Set, Tuple, Dict, List, Union, Optional

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIO import HwIO
from hwtHls.code import OP_ASHR, OP_LSHR, OP_SHL, OP_CTLZ, OP_CTTZ, OP_CTPOP
from hwtHls.frontend.ast.astToSsa import NetlistIoConstructorDictT
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, MachineInstr, MachineRegisterInfo, Register, \
    TargetOpcode, CmpInst, ConstantInt, TypeToIntegerType, TypeToArrayType, IntegerType, Type as LlvmType, ArrayType, \
    MachineLoopInfo, GlobalValue, ValueToConstantArray, ValueToConstantInt, ValueToConstantDataArray, ConstantArray
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOut_connectHlsIn_crossingHierarchy
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MachineEdge
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from tests.math.fp.hFloatTmpOps import OP_FADD, OP_FSUB, OP_FMUL, OP_FDIV


class HlsNetlistAnalysisPassMirToNetlistLowLevel(HlsNetlistAnalysisPass):
    """
    This object translates low level elements of LLVM MIR to hwtHls HlsNetlist
    
    :ivar valCache: cache for translated values which automatically construct HlsNetNodeOutLazy and replaces it once the value is resolved.
    :ivar _valueCopiedIntoElement: dictionary to avoid duplication of values which are copied into hierarchy containers
    :ivar _argIToIo: dictionary to speed up lookup of HwIO by Argument the Function
    :ivar placeholderObjectSlots: container python objects registered in frontend and passes into backend
    :ivar blockMeta: dictionary mapping :class:`MachineBasicBlock` to :class:`MachineBasicBlockMeta`
    :ivar edgeMeta: dictionary mapping :class:`MachineEdge` to :class:`MachineEdgeMeta`
    :ivar mf: translated :class:`MachineFunction`
    :ivar backedges: backedges of every loop
    :ivar liveness: dictionary for register liveness tracking
    :ivar registerTypes: dictionary for Register bitwidth lookup
    :ivar regToIo: dictionary for lookup of of HwIO by Register
    :ivar loops: :class:`MachineLoopInfo`
    """
    OPC_TO_OP = {
        TargetOpcode.HWTFPGA_ADD: HwtOps.ADD,
        TargetOpcode.HWTFPGA_SUB: HwtOps.SUB,
        TargetOpcode.HWTFPGA_MUL: HwtOps.MUL,
        TargetOpcode.HWTFPGA_UDIV: HwtOps.UDIV,
        TargetOpcode.HWTFPGA_SDIV: HwtOps.SDIV,
        TargetOpcode.HWTFPGA_AND: HwtOps.AND,
        TargetOpcode.HWTFPGA_OR: HwtOps.OR,
        TargetOpcode.HWTFPGA_XOR: HwtOps.XOR,
        TargetOpcode.HWTFPGA_NOT: HwtOps.NOT,

        TargetOpcode.G_ADD: HwtOps.ADD,
        TargetOpcode.G_SUB: HwtOps.SUB,
        TargetOpcode.G_MUL: HwtOps.MUL,
        TargetOpcode.G_UDIV: HwtOps.UDIV,
        TargetOpcode.G_SDIV: HwtOps.SDIV,
        TargetOpcode.G_AND: HwtOps.AND,
        TargetOpcode.G_OR: HwtOps.OR,
        TargetOpcode.G_XOR: HwtOps.XOR,

        TargetOpcode.HWTFPGA_ASHR: OP_ASHR,
        TargetOpcode.HWTFPGA_LSHR: OP_LSHR,
        TargetOpcode.HWTFPGA_SHL: OP_SHL,
        TargetOpcode.HWTFPGA_CTLZ: OP_CTLZ,
        TargetOpcode.HWTFPGA_CTLZ_ZERO_UNDEF: OP_CTLZ,
        TargetOpcode.HWTFPGA_CTTZ: OP_CTTZ,
        TargetOpcode.HWTFPGA_CTTZ_ZERO_UNDEF: OP_CTTZ,
        TargetOpcode.HWTFPGA_CTPOP: OP_CTPOP,
 
        TargetOpcode.G_ASHR: OP_ASHR,
        TargetOpcode.G_LSHR: OP_LSHR,
        TargetOpcode.G_SHL: OP_SHL,
        TargetOpcode.G_CTLZ: OP_CTLZ,
        TargetOpcode.G_CTLZ_ZERO_UNDEF: OP_CTLZ,
        TargetOpcode.G_CTTZ: OP_CTTZ,
        TargetOpcode.G_CTTZ_ZERO_UNDEF: OP_CTTZ,
        TargetOpcode.G_CTPOP: OP_CTPOP,
        
        TargetOpcode.HWTFPGA_FP_FADD: OP_FADD,
        TargetOpcode.HWTFPGA_FP_FSUB: OP_FSUB,
        TargetOpcode.HWTFPGA_FP_FMUL: OP_FMUL,
        TargetOpcode.HWTFPGA_FP_FDIV: OP_FDIV,
    }

    CMP_PREDICATE_TO_OP = {
        CmpInst.Predicate.ICMP_EQ: HwtOps.EQ,
        CmpInst.Predicate.ICMP_NE: HwtOps.NE,
        CmpInst.Predicate.ICMP_UGT: HwtOps.UGT,
        CmpInst.Predicate.ICMP_UGE: HwtOps.UGE,
        CmpInst.Predicate.ICMP_ULT: HwtOps.ULT,
        CmpInst.Predicate.ICMP_ULE: HwtOps.ULE,
        CmpInst.Predicate.ICMP_SGT: HwtOps.SGT,
        CmpInst.Predicate.ICMP_SGE: HwtOps.SGE,
        CmpInst.Predicate.ICMP_SLT: HwtOps.SLT,
        CmpInst.Predicate.ICMP_SLE: HwtOps.SLE,
    }
    OPC_TO_OP_SCHEDULING_RESOURCE = {
        TargetOpcode.HWTFPGA_MUX: HwtOps.TERNARY,
        TargetOpcode.HWTFPGA_EXTRACT: HwtOps.INDEX,
        TargetOpcode.HWTFPGA_MERGE_VALUES: HwtOps.CONCAT,
        **OPC_TO_OP
    }
    _HWTFPGA_CLOAD_CSTORE = (
        TargetOpcode.HWTFPGA_CLOAD,
        TargetOpcode.HWTFPGA_CSTORE,
    )
    _BITCOUNT_OPCODES = {
        TargetOpcode.HWTFPGA_CTLZ,
        TargetOpcode.HWTFPGA_CTLZ_ZERO_UNDEF,
        TargetOpcode.HWTFPGA_CTTZ,
        TargetOpcode.HWTFPGA_CTTZ_ZERO_UNDEF,
        TargetOpcode.HWTFPGA_CTPOP,
    }
    _FP_BIN_OPCODES = {
        TargetOpcode.HWTFPGA_FP_FADD,
        TargetOpcode.HWTFPGA_FP_FSUB,
        TargetOpcode.HWTFPGA_FP_FMUL,
        TargetOpcode.HWTFPGA_FP_FDIV,
    }

    def __init__(self, hls: "HlsScope", tr: ToLlvmIrTranslator,
                 mf: MachineFunction,
                 backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                 liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                 ioRegs: List[Register],
                 registerTypes: Dict[Register, int],
                 loops: MachineLoopInfo,
                 netlist: HlsNetlistCtx,
                 ioNodeConstructors: NetlistIoConstructorDictT,
                 dbgTracer: Optional[DebugTracer],
                 ):
        super(HlsNetlistAnalysisPassMirToNetlistLowLevel, self).__init__()
        self.netlist = netlist
        # :note: value of a block in block0 means that the control flow was passed to block0 from block
        self.valCache = MirToHwtHlsNetlistValueCache(netlist)
        self._valueCopiedIntoElement: Dict[Tuple[HlsNetNodeAggregate, MachineBasicBlock, Register]] = {}

        argToArgIndex = {a: i for (i, a) in enumerate(tr.llvm.main.args())}
        self._argIToIo = {argToArgIndex[a]: io for (io, (a, _, _)) in tr.ioToVar.items()}
        self.placeholderObjectSlots = [obj for (obj, _) in tr.placeholderObjectSlots]
        self.blockMeta: Dict[MachineBasicBlock, MachineBasicBlockMeta] = {}
        self.edgeMeta: Dict[MachineEdge, MachineEdgeMeta] = {}
        self.mf = mf
        self.backedges = backedges
        self.liveness = liveness
        self.registerTypes = registerTypes
        self.regToIo: Dict[Register, HwIO] = {ioRegs[ai]: io for (ai, io) in self._argIToIo.items()}
        self.ioNodeConstructors: NetlistIoConstructorDictT = ioNodeConstructors
        self.loops = loops
        # register self in netlist analysis cache
        netlist._analysis_cache[self.__class__] = self
        self.dbgTracer: Optional[DebugTracer] = dbgTracer

    def _getSchedulingResourceForInstruction(self, MRI: MachineRegisterInfo, instr: MachineInstr):
        opc = instr.getOpcode()
        opDef = self.OPC_TO_OP.get(opc, None)
        if opDef is not None:
            return opDef
        elif opc == TargetOpcode.HWTFPGA_CLOAD or \
             opc == TargetOpcode.HWTFPGA_CSTORE:
            baseAddrOp = instr.getOperand(1)
            assert baseAddrOp.isReg(), instr
            r = baseAddrOp.getReg()
            io = self.regToIo.get(r, None)
            if io is not None:
                return io
            # could still be load or write from ROM
        elif opc == TargetOpcode.HWTFPGA_ICMP:
            predicate = CmpInst.Predicate(instr.getOperand(1).getPredicate())
            return self.CMP_PREDICATE_TO_OP[predicate]

        return None

    def _constructBuffer(self, name: str,
                         srcBlock: MachineBasicBlock,
                         dstBlock: MachineBasicBlock,
                         cacheKey,
                         val: Union[HlsNetNodeOutAny, HConst],
                         isBackedge: bool=False,
                         isControl: bool=False,
                         addWriteToOrderingChain=True) -> HlsNetNodeOut:
        namePrefix = f"bb{srcBlock.getNumber():d}_to_bb{dstBlock.getNumber():d}_{name:s}"
        rCls = HlsNetNodeReadBackedge if isBackedge else HlsNetNodeReadForwardedge
        rFromIn = rCls(
            self.netlist,
            val._dtype,
            name=f"{namePrefix:s}_dst",
        )
        dstBlockMeta: MachineBasicBlockMeta = self.blockMeta[dstBlock]
        dstBlockMeta.parentElement.addNode(rFromIn)

        rFromIn = rFromIn._portDataOut
        if isControl and HdlType_isVoid(val._dtype):
            rFromIn = rFromIn.obj.getValidNB()
            # add as a src to all dependencies of orderingIn where this read exists
            orderingIn = dstBlockMeta.orderingIn
            assert isinstance(orderingIn, HlsNetNodeOutLazy), orderingIn
            orderingIn: HlsNetNodeOutLazy
            if orderingIn.dependent_inputs:
                oo = rFromIn.obj.getOrderingOutPort()
                for user in orderingIn.dependent_inputs:
                    userObj = user.obj
                    userObj: HlsNetNodeExplicitSync
                    oo.connectHlsIn(userObj._addInput("orderingIn"))

        if cacheKey is not None:
            self.valCache.add(dstBlock, cacheKey, rFromIn, False)

        wCls = HlsNetNodeWriteBackedge if isBackedge else HlsNetNodeWriteForwardedge
        wToOut = wCls(
            self.netlist,
            name=f"{namePrefix:s}_src")
        srcBlockMeta = self.blockMeta[srcBlock]
        srcBlockMeta.parentElement.addNode(wToOut)
        if isinstance(val, HConst):
            val = srcBlockMeta.parentElement.builder.buildConst(val)
        val.connectHlsIn(wToOut._inputs[0])
        if isBackedge:
            oi = wToOut._addInput("orderingIn", True)
            HlsNetNodeOut_connectHlsIn_crossingHierarchy(rFromIn.obj.getOrderingOutPort(), oi, "ordering")
        else:
            oi = rFromIn.obj._addInput("orderingIn", True)
            HlsNetNodeOut_connectHlsIn_crossingHierarchy(wToOut.getOrderingOutPort(), oi, "ordering")

        wToOut.associateRead(rFromIn.obj)
        wToOut.buffName = f"{namePrefix:s}_backedge_buff"

        if addWriteToOrderingChain:
            srcBlockMeta.addOrderedNodeForControlWrite(wToOut, dstBlockMeta)

        if cacheKey is not None:
            # because we need to use latest value not the input value which we just added (rFromIn)
            return self.valCache.get(dstBlock, cacheKey, rFromIn._dtype)

        return rFromIn

    def _translateType(self, t: LlvmType):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return HBits(it.getBitWidth())
        at = TypeToArrayType(t)
        if at is not None:
            at: ArrayType
            elmT = self._translateType(at.getElementType())
            return elmT[at.getNumElements()]
        else:
            raise NotImplementedError(t)

    def _translateConstant(self, builder: HlsNetlistBuilder, c: ConstantInt):
        val = int(c.getValue())
        t = self._translateType(c.getType())
        if not t.signed and val < 0:  # convert to unsigned
            val = t.all_mask() + val + 1
        v = t.from_py(val)
        return builder.buildConst(v)

    @classmethod
    def _translateConstantArrayToPy(cls, t: HArray, arr: ConstantArray):
        element_t = t.element_t
        res = []
        if isinstance(element_t, HArray):
            for elmVals in arr.iterOperands():
                res.append(cls._normalizeArrayVal(element_t, ValueToConstantArray(elmVals.get())))
        elif not element_t.signed:
            # convert to unsigned if required
            m = element_t.all_mask()
            for v in arr:
                v = int(ValueToConstantInt(v).getValue())
                if v < 0:
                    v = m + v + 1
                res.append(v)
        else:
            for v in arr:
                v = int(ValueToConstantInt(v).getValue())
                res.append(v)
        return res

    def _translateGlobal(self, builder:HlsNetlistBuilder, g: GlobalValue):
        val = g.getOperand(0)
        t = self._translateType(val.getType())
        if not isinstance(t, HArray):
            raise NotImplementedError(t)
        arrVal = ValueToConstantArray(val)
        if arrVal is None:
            arrVal = ValueToConstantDataArray(val)
        assert arrVal is not None, (val.__class__, val)
        pyVal = self._translateConstantArrayToPy(t, arrVal)
        v = t.from_py(pyVal)
        c = builder.buildConst(v)
        c.obj.name = g.getName().str()
        return c

    # def _translateIntBits(self, builder: HlsNetlistBuilder, val: int, dtype: HBits):
    #    v = dtype.from_py(val)
    #    return builder.buildConst(v)
    #
    # def _translateIntBit(self, builder: HlsNetlistBuilder, val: int):
    #    return self._translateIntBits(builder, val, BIT)

    def _translateRegister(self, block: MachineBasicBlock, r: Register):
        bw = self.registerTypes.get(r, None)
        res = self.valCache.get(block, r, HBits(bw))
        assert isinstance(res, (HlsNetNodeOut, HlsNetNodeOutLazy)), res
        return res

    def _translateMBB(self, block: MachineBasicBlock):
        return self.valCache.get(block, block, BIT)

    def _addExtraCond(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite],
                      cond: Union[HlsNetNodeOutAny, bool, None],
                      blockEn: Optional[HlsNetNodeOutAny]):
        if cond is None or isinstance(cond, int):
            assert cond is None or cond == 1, cond
            if blockEn is None:
                return
            cond = blockEn
        elif blockEn is not None:
            cond = n.getHlsNetlistBuilder().buildAnd(blockEn, cond)

        n.addControlSerialExtraCond(cond)

    def _addSkipWhen_n(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite],
                       cond_n: Union[HlsNetNodeOutAny, bool, None],
                       blockEn: Optional[HlsNetNodeOutAny]):
        """
        add skipWhen condition to read or write, the condition itself is negated
        """
        b = n.getHlsNetlistBuilder()
        blockEn_n = None if blockEn is None else b.buildNot(blockEn)
        if cond_n is None or isinstance(cond_n, int):
            assert cond_n is None or cond_n == 1, cond_n
            if blockEn_n is None:
                return
            cond = blockEn_n
        else:
            cond = b.buildNot(cond_n)
            if blockEn_n is not None:
                cond = b.buildOr(blockEn_n, cond)

        n.addControlSerialSkipWhen(cond)

