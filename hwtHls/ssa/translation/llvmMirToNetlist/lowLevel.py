from typing import Set, Tuple, Dict, List, Union, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.array import HArray
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.synthesizer.interface import Interface
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, Register, \
    TargetOpcode, CmpInst, ConstantInt, TypeToIntegerType, TypeToArrayType, IntegerType, Type as LlvmType, ArrayType, \
    MachineLoopInfo, GlobalValue, ValueToConstantArray, ValueToConstantInt, ValueToConstantDataArray, ConstantArray
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks, \
    DataFlowThread
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    link_hls_nodes, HlsNetNodeOutAny, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.observableList import ObservableList
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MachineEdge
from hwtHls.ssa.translation.llvmMirToNetlist.resetValueExtract import ResetValueExtractor
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class HlsNetlistAnalysisPassMirToNetlistLowLevel(HlsNetlistAnalysisPass):
    """
    This object translates low level elements of LLVM MIR to hwtHls HlsNetlist
    """
    OPC_TO_OP = {
        TargetOpcode.HWTFPGA_ADD: AllOps.ADD,
        TargetOpcode.HWTFPGA_SUB: AllOps.SUB,
        TargetOpcode.HWTFPGA_MUL: AllOps.MUL,
        TargetOpcode.HWTFPGA_UDIV: AllOps.UDIV,
        TargetOpcode.HWTFPGA_SDIV: AllOps.SDIV,
        TargetOpcode.HWTFPGA_AND: AllOps.AND,
        TargetOpcode.HWTFPGA_OR: AllOps.OR,
        TargetOpcode.HWTFPGA_XOR: AllOps.XOR,
        TargetOpcode.HWTFPGA_NOT: AllOps.NOT,
    }
    CMP_PREDICATE_TO_OP = {
        CmpInst.Predicate.ICMP_EQ:AllOps.EQ,
        CmpInst.Predicate.ICMP_NE:AllOps.NE,
        CmpInst.Predicate.ICMP_UGT:AllOps.UGT,
        CmpInst.Predicate.ICMP_UGE:AllOps.UGE,
        CmpInst.Predicate.ICMP_ULT:AllOps.ULT,
        CmpInst.Predicate.ICMP_ULE:AllOps.ULE,
        CmpInst.Predicate.ICMP_SGT:AllOps.SGT,
        CmpInst.Predicate.ICMP_SGE:AllOps.SGE,
        CmpInst.Predicate.ICMP_SLT:AllOps.SLT,
        CmpInst.Predicate.ICMP_SLE:AllOps.SLE,
    }

    def __init__(self, hls: "HlsScope", tr: ToLlvmIrTranslator,
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
        self.builder = HlsNetlistBuilder(netlist)
        netlist._setBuilder(self.builder)
        self.valCache = MirToHwtHlsNetlistValueCache(netlist)
        aargToArgIndex = {a: i for (i, a) in enumerate(tr.llvm.main.args())}
        self._argIToIo = {aargToArgIndex[a]: io for (io, (a, _, _)) in tr.ioToVar.items()}
        self.blockSync: Dict[MachineBasicBlock, MachineBasicBlockMeta] = {}
        self.edgeMeta: Dict[MachineEdge, MachineEdgeMeta] = {}
        self.nodes: ObservableList[HlsNetNode] = netlist.nodes
        self.inputs: ObservableList[HlsNetNodeRead] = netlist.inputs
        self.outputs: ObservableList[HlsNetNodeWrite] = netlist.outputs
        self.mf = mf
        self.backedges = backedges
        self.liveness = liveness
        self.registerTypes = registerTypes
        self.regToIo: Dict[Register, Interface] = {ioRegs[ai]: io for (ai, io) in self._argIToIo.items()}
        self.loops = loops
        self.translatedBranchConditions: Dict[MachineBasicBlock, Dict[Register, HlsNetNodeOutAny]] = {}
        # register self in netlist analysis cache
        netlist._analysis_cache[self.__class__] = self

    def _constructBackedgeBuffer(self, name: str,
                                 srcBlock: MachineBasicBlock,
                                 dstBlock: MachineBasicBlock,
                                 cacheKey,
                                 val: HlsNetNodeOutAny,
                                 isControl: bool=False) -> HlsNetNodeOut:
        # we need to insert backedge buffer to get block en flag from pred to mb
        namePrefix = f"bb{srcBlock.getNumber():d}_to_bb{dstBlock.getNumber():d}_{name:s}"
        rFromIn = HlsNetNodeReadBackedge(
            self.netlist,
            val._dtype,
            name=f"{namePrefix:s}_dst",
        )
        self.inputs.append(rFromIn)
        rFromIn = rFromIn._outputs[0]
        if isControl and HdlType_isVoid(val._dtype):
            rFromIn.obj.setNonBlocking()
            rFromIn = rFromIn.obj.getValidNB()
            # add as a src to all dependencies of orderingIn where this read exists
            dstBlockSync: MachineBasicBlockMeta = self.blockSync[dstBlock]
            orderingIn = dstBlockSync.orderingIn
            assert isinstance(orderingIn, HlsNetNodeOutLazy), orderingIn
            orderingIn: HlsNetNodeOutLazy
            if orderingIn.dependent_inputs:
                oo = rFromIn.obj.getOrderingOutPort()
                for user in orderingIn.dependent_inputs:
                    userObj = user.obj
                    userObj: HlsNetNodeExplicitSync
                    link_hls_nodes(oo, userObj._addInput("orderingIn"))

        if cacheKey is not None:
            self.valCache.add(dstBlock, cacheKey, rFromIn, False)

        wToOut = HlsNetNodeWriteBackedge(
            self.netlist,
            name=f"{namePrefix:s}_src")
        link_hls_nodes(val, wToOut._inputs[0])
        oi = wToOut._addInput("orderingIn", True)
        link_hls_nodes(rFromIn.obj.getOrderingOutPort(), oi)
        self.outputs.append(wToOut)

        wToOut.associateRead(rFromIn.obj)
        wToOut.buffName = f"{namePrefix:s}_backedge_buff"
        srcMbSync = self.blockSync[srcBlock]
        srcMbSync.addOrderedNodeForControlWrite(wToOut, self.blockSync[dstBlock])

        if cacheKey is not None:
            # because we need to use latest value not the input value which we just added (rFromIn)
            return self.valCache.get(dstBlock, cacheKey, rFromIn._dtype)

        return rFromIn

    def _translateType(self, t: LlvmType):
        it = TypeToIntegerType(t)
        if it is not None:
            it: IntegerType
            return Bits(it.getBitWidth())
        at = TypeToArrayType(t)
        if at is not None:
            at: ArrayType
            elmT = self._translateType(at.getElementType())
            return elmT[at.getNumElements()]
        else:
            raise NotImplementedError(t)

    def _translateConstant(self, c: ConstantInt):
        val = int(c.getValue())
        t = self._translateType(c.getType())
        if not t.signed and val < 0:  # convert to unsigned
            val = t.all_mask() + val + 1
        v = t.from_py(val)
        return self.builder.buildConst(v)

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
            for v in arr.iterOperands():
                v = int(ValueToConstantInt(v.get()).getValue())
                if v < 0:
                    v = m + v + 1
                res.append(v)
        else:
            for v in arr.iterOperands():
                v = int(ValueToConstantInt(v.get()).getValue())
                res.append(v)
        return res

    def _translateGlobal(self, g: GlobalValue):
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
        c = self.builder.buildConst(v)
        c.obj.name = g.getName().str()
        return c

    def _translateIntBits(self, val: int, dtype: Bits):
        v = dtype.from_py(val)
        return self.builder.buildConst(v)

    def _translateIntBit(self, val: int):
        return self._translateIntBits(val, BIT)

    def _translateRegister(self, block: MachineBasicBlock, r: Register):
        bw = self.registerTypes.get(r, None)
        res = self.valCache.get(block, r, Bits(bw))
        assert isinstance(res, (HlsNetNodeOut, HlsNetNodeOutLazy)), res
        return res

    def _translateMBB(self, block: MachineBasicBlock):
        return self.valCache.get(block, block, BIT)

    def _addExtraCond(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite],
                      cond: Union[int, HlsNetNodeOutAny],
                      blockEn: Optional[HlsNetNodeOutAny]):
        if isinstance(cond, int):
            assert cond == 1, cond
            if blockEn is None:
                return
            cond = blockEn
        elif blockEn is not None:
            cond = self.builder.buildOp(AllOps.AND, BIT, blockEn, cond)

        n.addControlSerialExtraCond(cond)

    def _addSkipWhen_n(self, n: Union[HlsNetNodeRead, HlsNetNodeWrite], cond_n: Union[int, HlsNetNodeOutAny], blockEn: Optional[HlsNetNodeOutAny]):
        """
        add skipWhen condition to read or write, the condition itself is negated
        """
        b = self.builder
        blockEn_n = None if blockEn is None else b.buildOp(AllOps.NOT, BIT, blockEn)
        if isinstance(cond_n, int):
            assert cond_n == 1, cond_n
            if blockEn_n is None:
                return
            cond = blockEn_n
        else:
            cond = b.buildOp(AllOps.NOT, BIT, cond_n)
            if blockEn_n is not None:
                cond = b.buildOp(AllOps.OR, BIT, blockEn_n, cond)

        n.addControlSerialSkipWhen(cond)

    def _replaceInputDriverWithConst1b(self, i: HlsNetNodeIn, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        return ResetValueExtractor._replaceInputDriverWithConst1b(self, i, threads)

    def _getThreadOfReg(self, threads: HlsNetlistAnalysisPassDataThreadsForBlocks,
                        mb: MachineBasicBlock, reg: Register, dtype: HdlType) -> Optional[DataFlowThread]:
        """
        Get thread where the register is used.
        HVoidOrdering outputs and lazy outputs are ignored and for them this function returns None.
        """
        nodeOut: HlsNetNodeOutAny = self.valCache.get(mb, reg, dtype)
        obj = nodeOut if isinstance(nodeOut, HlsNetNodeOutLazy) else nodeOut.obj
        t, newlyAdded = threads.searchForThreads(obj)
        if newlyAdded:
            threads.threadsPerBlock[mb].append(t)
            threads.threadIdToBlock[id(t)] = [mb]
        return t

