from typing import Set, Tuple, Dict, List, Union, Type

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.pyUtils.arrayQuery import grouper
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.unit import Unit
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, MachineOperand, Register, \
    MachineInstr, TargetOpcode, CmpInst, ConstantInt, TypeToIntegerType, IntegerType, Type as LlvmType
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HOrderingVoidT, HlsNetNodeRead, \
    HlsNetNodeWrite
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    link_hls_nodes, HlsNetNodeOutAny, HlsNetNodeIn
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.utils import hls_op_and, hls_op_or_variadic, hls_op_not
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.opCache import MirToHwtHlsNetlistOpCache
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class MirToNetlist():
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

    def __init__(self, hls: "HlsStreamProc", tr: ToLlvmIrTranslator):
        self.netlist: HlsNetlistCtx = HlsNetlistCtx(hls.parentUnit, hls.freq)
        # :note: value of a block in block0 means that the control flow was passed to block0 from block 
        self.valCache = MirToHwtHlsNetlistOpCache()
        aargToArgIndex = {a: i for (i, a) in enumerate(tr.llvm.main.args())}
        self._argIToIo = {aargToArgIndex[a]: io for (io, a) in tr.ioToVar.items()}
        self.blockSync: Dict[MachineBasicBlock, MachineBasicBlockSyncContainer] = {}
        self.nodes: List[HlsNetNode] = self.netlist.nodes
        self.inputs: List[HlsNetNodeRead] = self.netlist.inputs
        self.outputs: List[HlsNetNodeWrite] = self.netlist.outputs
        self.regToIo: Dict[Register, Interface] = {}

    def toNetlist(self, mf: MachineFunction,
                  backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                  liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                  ioRegs: List[Register],
                  registerTypes: Dict[Register, int]
                  ):
        self.registerTypes = registerTypes
        self.regToIo = {ioRegs[ai]: io for (ai, io) in self._argIToIo.items()}
        
        # print(mf)
        # print(backedges)
        # print(liveness)
        # print(ioRegs)
        self._translateDatapathInBlocks(mf)
        self._translateControlAndInterBlockConnections(mf, backedges, liveness)

    def _translateDatapathInBlocks(self, mf: MachineFunction):
        valCache: MirToHwtHlsNetlistOpCache = self.valCache 
        netlist: HlsNetlistCtx = self.netlist
        for mb in mf:
            mb: MachineBasicBlock
            mbSync = MachineBasicBlockSyncContainer(
                mb,
                HlsNetNodeOutLazy([], valCache, BIT),
                HlsNetNodeOutLazy([], valCache, HOrderingVoidT))
            self.blockSync[mb] = mbSync
            for instr in mb:
                instr: MachineInstr
                dst = None
                ops = []
                for mo in instr.operands():
                    mo: MachineOperand
                    if mo.isReg():
                        if mo.isDef():
                            assert dst is None, (dst, instr)
                            dst = mo.getReg()
                        else:
                            ops.append(self._translateRegister(mb, mo.getReg()))

                    elif mo.isMBB():
                        ops.append(self._translateMBB(mo.getMBB()))
                    elif mo.isImm():
                        ops.append(mo.getImm())
                    elif mo.isCImm():
                        ops.append(self._translateConstant(mo.getCImm()))
                    elif mo.isPredicate():
                        ops.append(CmpInst.Predicate(mo.getPredicate()))
                    else:
                        raise NotImplementedError(instr, mo)

                opc = instr.getOpcode()
                opDef = self.OPC_TO_OP.get(opc, None)
                if opDef is not None:
                    resT = ops[0]._dtype
                    n = HlsNetNodeOperator(netlist, opDef, len(ops), resT)
                    self.nodes.append(n)
                    for i, arg in zip(n._inputs, ops):
                        # a = self.to_hls_expr(arg)
                        link_hls_nodes(arg, i)
                    valCache.add(mb, dst, n._outputs[0], True)
                    continue

                elif opc == TargetOpcode.GENFPGA_MUX:
                    resT = ops[0]._dtype
                    argCnt = len(ops)
                    if argCnt == 1:
                        valCache.add(mb, dst, ops[0], True)

                    else:
                        mux = HlsNetNodeMux(self.netlist, resT)
                        self.nodes.append(mux)
                        if argCnt % 2 != 1:
                            ops.append(self._translateRegister(mb, dst))

                        for (src, cond) in grouper(2, ops):
                            if cond is not None:
                                # [todo] inject block en to cond
                                mux._add_input_and_link(cond)

                            mux._add_input_and_link(src)
                            
                        valCache.add(mb, dst, mux._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_CLOAD:
                    src, cond = ops
                    assert isinstance(src, Interface), src
                    n = HlsNetNodeRead(netlist, src)
                    if isinstance(cond, int):
                        assert cond == 1, cond
                    else:
                        n.add_control_extraCond(cond)
                    mbSync.addOrderedNode(n)
                    self.inputs.append(n)
                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.GENFPGA_CSTORE:
                    srcVal, dstIo, cond = ops
                    assert isinstance(dstIo, Interface), dstIo
                    n = HlsNetNodeWrite(netlist, srcVal, dstIo)
                    if isinstance(cond, int):
                        assert cond == 1, cond
                    else:
                        n.add_control_extraCond(cond)
                    mbSync.addOrderedNode(n)
                    self.outputs.append(n)

                elif opc == TargetOpcode.G_ICMP:
                    predicate, lhs, rhs = ops
                    opDef = self.CMP_PREDICATE_TO_OP[predicate]
                    if predicate in self.SIGNED_CMP_OPS:
                        raise NotImplementedError()
                    n = HlsNetNodeOperator(netlist, opDef, 2, BIT)
                    self.nodes.append(n)
                    for i, arg in zip(n._inputs, (lhs, rhs)):
                        link_hls_nodes(arg, i)
                    valCache.add(mb, dst, n._outputs[0], True)

                elif opc == TargetOpcode.G_BR or opc == TargetOpcode.G_BRCOND:
                    # c = self._translateIntBit(1)
                    # for suc in mb.successors():
                    #    valCache.add(mb, suc, c._outputs[0], True)

                    pass  # will be translated in next step when control is generated

                else:
                    raise NotImplementedError(instr)

    def _translateControlAndInterBlockConnections(self, mf: MachineFunction,
                          backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                          liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                          ):
        valCache: MirToHwtHlsNetlistOpCache = self.valCache 
        
        for mb in mf:
            mb: MachineBasicBlock
            # resolve control enable flag for a block
            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            if mb.pred_size() == 0:
                # add starter
                n = HlsProgramStarter(self.netlist)
                self.nodes.append(n)
                blockEn = n._outputs[0]
            else:
                # construct CFG flags
                enFromPredccs = []  # list of control en flag from any predecessor
                for pred in mb.predecessors():
                    pred: MachineBasicBlock
                    predEn = self.blockSync[pred].blockEn
                    brCond = None
                    for ter in pred.terminators():
                        ter: MachineInstr
                        opc = ter.getOpcode()
                        assert brCond is None, brCond
                        predEn = self.blockSync[pred].blockEn
                    
                        if opc == TargetOpcode.G_BR:
                            # mb is only successor of pred, we can use en of pred block
                            pass
                        
                        elif opc == TargetOpcode.G_BRCOND:
                            # mb is conditional successor of pred, we need to use end of pred and branch cond to get en fo mb
                            c, dstBlock = ter.operands()
                            assert c.isReg(), c 
                            assert dstBlock.isMBB(), dstBlock
                            c = c.getReg()
                            dstBlock = dstBlock.getMBB()
                            if dstBlock != mb:
                                c = hls_op_not(self.netlist, c)
                            brCond = hls_op_and(self.netlist, predEn, c)
                        else:
                            raise NotImplementedError("Unknown terminator", ter)

                    if brCond is None:
                        brCond = predEn

                    if (pred, mb) in backedges:
                        # we need to insert backedge buffer to get block en flag from pred to mb
                        # [fixme] write order must be asserted because we can not release a control token until all block operations finished
                        brCond = self._constructBackedgeBuffer("c", pred, mb, pred, brCond)
                    else:
                        valCache.add(mb, pred, brCond, True)

                    enFromPredccs.append(brCond)

                blockEn = hls_op_or_variadic(self.netlist, *enFromPredccs)

            assert isinstance(mbSync.blockEn, HlsNetNodeOutLazy), (mbSync.blockEn, "Must not be resolved yet")
            mbSync.blockEn.replace_driver(blockEn)
            mbSync.blockEn = blockEn

            # Construct block input MUXes.
            # the liveIns are not required to be same because in some cases
            # the libeIn is used only by MUX input for a specific predecessor
            # First we collect all inputs for all variant then we build MUX.
            liveInOrder = []  # list of liveIn variables so we process them in deterministic order
            # liveIn -> List[Tuple[value, condition]]
            liveIns: Dict[Register, List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]]] = {}
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                isBackedge = (pred, mb) in backedges

                for liveIn in liveness[pred][mb]:
                    liveIn: Register
                    if liveIn in self.regToIo:
                        continue  # we will use interface not the value of address where it is mapped

                    caseList = liveIns.get(liveIn, None)
                    if caseList is None:
                        # we step upon a new liveIn variable, we create a list for its values
                        liveInOrder.append(liveIn)
                        caseList = liveIns[liveIn] = []

                    caseList: List[Tuple[HlsNetNodeOutAny, HlsNetNodeOutAny]]
                    dtype = Bits(self.registerTypes[liveIn])
                    v = valCache.get(pred, liveIn, dtype)
                    if isBackedge:
                        v = self._constructBackedgeBuffer(f"r_{liveIn.id():d}", pred, mb, (pred, liveIn), v)
                    c = valCache.get(mb, pred, BIT)
                    caseList.append((v, c))

            predCnt = mb.pred_size()
            for liveIn in liveInOrder:
                liveIn: Register
                cases = liveIns[liveIn]
                assert cases, ("MUX for liveIn has to have some cases (even if it is undef)", liveIn)
                if predCnt == 1:
                    assert len(cases) == 1
                    v, _ = cases[0]
                else:
                    dtype = Bits(self.registerTypes[liveIn])
                    mux = HlsNetNodeMux(self.netlist, dtype)
                    self.nodes.append(mux)

                    for last, (src, cond) in iter_with_last(cases):
                        if not last:
                            # last case must be always satisfied because the block must have been entered somehow
                            mux._add_input_and_link(cond)

                        mux._add_input_and_link(src)
                        
                    v = mux._outputs[0]

                valCache.add(mb, liveIn, v, False)
            
        # finalize ordering connections after all IO is instantiated
        for mb in mf:
            mb: MachineBasicBlock
            orderingInputs = []
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                if (pred, mb) not in backedges:
                    o = self.blockSync[pred].orderingOut
                    if o is not None:
                        orderingInputs.append(o)

            mbSync: MachineBasicBlockSyncContainer = self.blockSync[mb]
            if not orderingInputs:
                # must remove ordering because this is a first ordered operation and it does not have any ordering dependence
                for i in mbSync.orderingIn.dependent_inputs:
                    i.obj._removeInput(i.in_i)

                if mbSync.orderingIn is mbSync.orderingOut:
                    mbSync.orderingOut = None
                mbSync.orderingIn = None
            else:
                for last, i in iter_with_last(orderingInputs):
                    if last:
                        mbSync.orderingIn.replace_driver(i)
                    else:
                        for depI in mbSync.orderingIn.dependent_inputs:
                            depI: HlsNetNodeIn
                            # create a new input for ordering connection
                            depI2 = depI.obj._add_input()
                            link_hls_nodes(i, depI2)
            
    def _constructBackedgeBuffer(self, name: str, srcBlock: MachineBasicBlock, dstBlock: MachineBasicBlock, cacheKey, val: HlsNetNodeOutAny) -> HlsNetNodeOut:
        # we need to insert backedge buffer to get block en flag from pred to mb
        srcName = srcBlock.getName().str()
        dstName = dstBlock.getName().str()
        _, r_from_in = self._add_hs_intf_and_read(
            f"{name:s}_{srcName:s}_to_{dstName:s}_out",
            val._dtype,
            HlsNetNodeReadBackwardEdge)
        self.valCache.add(dstBlock, cacheKey, r_from_in, False)
        
        _, w_to_out = self._add_hs_intf_and_write(f"c_buff_{srcName:s}_to_{dstName:s}_in", val._dtype,
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


class SsaPassLlvmToMirAndMirToNetlist(SsaPass):

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa") -> HlsNetlistCtx:
        tr: ToLlvmIrTranslator = to_ssa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        toNetlist = MirToNetlist(hls, tr)
        tr.llvm.runOpt(toNetlist.toNetlist)
        return toNetlist.netlist
