from typing import Tuple, Dict, List, Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT, SLICE, INT
from hwtHls.frontend.ast.astToSsa import NetlistIoConstructorDictT
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineFunction, MachineBasicBlock, Register, \
    MachineInstr, MachineOperand, CmpInst, TargetOpcode
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.insideOfBlockSyncTracker import InsideOfBlockSyncTracker
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MACHINE_EDGE_TYPE
from hwtHls.ssa.translation.llvmMirToNetlist.utils import LiveInMuxMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache

BlockLiveInMuxSyncDict = Dict[Tuple[MachineBasicBlock, MachineBasicBlock, Register], HlsNetNodeExplicitSync]


class HlsNetlistAnalysisPassMirToNetlistDatapath(HlsNetlistAnalysisPassMirToNetlistLowLevel):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist
    """
    _HWTFPGA_CLOAD_CSTORE = (TargetOpcode.HWTFPGA_CLOAD, TargetOpcode.HWTFPGA_CSTORE)

    def translateDatapathInBlocks(self, mf: MachineFunction, ioNodeConstructors: NetlistIoConstructorDictT):
        """
        Translate all non control instructions which are entirely in some block.
        (Excluding connections between blocks)
        """
        HlsNetlistAnalysisPassBlockSyncType.constructBlockMeta(mf, self.netlist, self.valCache, self.blockSync)
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
        builder: HlsNetlistBuilder = self.builder
        MRI = mf.getRegInfo()
        assert not self.translatedBranchConditions

        for mb in mf:
            mb: MachineBasicBlock
            mbSync = self.blockSync[mb]
            syncTracker = InsideOfBlockSyncTracker(mbSync.blockEn, builder)
            translatedBranchConditions = self.translatedBranchConditions[mb] = {}
            # construct lazy output for liveIns in advance to assert that we have lazy input to replace later
            # with a liveIn mux
            seenLiveIns: Set[Register] = set()
            blockBoudary = syncTracker.blockBoudary
            for pred in mb.predecessors():
                for liveIn in sorted(self.liveness[pred][mb], key=lambda li: li.virtRegIndex()):
                    if self._regIsValidLiveIn(MRI, liveIn) and liveIn not in seenLiveIns:
                        dtype = Bits(self.registerTypes[liveIn])
                        liveInO = valCache.get(mb, liveIn, dtype)
                        blockBoudary.add(liveInO)
                        seenLiveIns.add(liveIn)

            for instr in mb:
                instr: MachineInstr
                opc = instr.getOpcode()
                if opc == TargetOpcode.HWTFPGA_ARG_GET:
                    continue

                dst = None
                ops = []
                isLoadOrStore = opc in self._HWTFPGA_CLOAD_CSTORE
                for i, mo in enumerate(instr.operands()):
                    mo: MachineOperand
                    if mo.isReg():
                        r = mo.getReg()
                        if mo.isDef():
                            assert dst is None, (dst, instr)
                            dst = r
                        elif isLoadOrStore and i == 1:
                            io = self.regToIo.get(r, None)
                            if io is not None:
                                ops.append(io)
                                continue

                            addrDefMO = MRI.getOneDef(r)
                            assert addrDefMO is not None, instr
                            addrDefInstr = addrDefMO.getParent()
                            addrDefOpc = addrDefInstr.getOpcode()
                            assert addrDefOpc == TargetOpcode.HWTFPGA_GLOBAL_VALUE
                            op = valCache._toHlsCache[(addrDefInstr.getParent(), addrDefMO.getReg())]
                            ops.append(op)
                        else:
                            isUndef = r not in self.regToIo and MRI.def_empty(r)
                            if not isUndef:
                                rDef = MRI.getOneDef(r)
                                isUndef = rDef is not None and rDef.getParent().getOpcode() == TargetOpcode.IMPLICIT_DEF

                            if isUndef:
                                bw = self.registerTypes[r]
                                op = builder.buildConst(Bits(bw).from_py(None))
                            else:
                                op = self._translateRegister(mb, r)
                            ops.append(op)

                    elif mo.isMBB():
                        ops.append(self._translateMBB(mo.getMBB()))
                    elif mo.isImm():
                        ops.append(mo.getImm())
                    elif mo.isCImm():
                        ops.append(self._translateConstant(mo.getCImm()))
                    elif mo.isPredicate():
                        ops.append(CmpInst.Predicate(mo.getPredicate()))
                    elif mo.isGlobal():
                        ops.append(self._translateGlobal(mo.getGlobal()))
                    else:
                        raise NotImplementedError(instr, mo)

                if dst is None:
                    name = None
                else:
                    name = f"bb{mb.getNumber()}_r{dst.virtRegIndex():d}"

                res = None
                opDef = self.OPC_TO_OP.get(opc, None)
                if opDef is not None:
                    resT = ops[0]._dtype
                    res = builder.buildOp(opDef, resT, *ops)
                    res.obj.name = name
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_MUX:
                    resT = ops[0]._dtype
                    argCnt = len(ops)
                    if argCnt == 1:
                        valCache.add(mb, dst, ops[0], True)

                    else:
                        if argCnt % 2 != 1:
                            # add current value as a default option in MUX
                            ops.append(self._translateRegister(mb, dst))

                        res = builder.buildMux(resT, tuple(ops))
                        res.obj.name = name
                        valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_CLOAD:
                    # load from data channel
                    srcIo, index, cond = ops  # [todo] implicit operands
                    if isinstance(srcIo, HlsNetNodeOut):
                        res = builder.buildOp(AllOps.INDEX, srcIo._dtype.element_t, srcIo, index)
                        if isinstance(cond, int):
                            assert cond == 1, instr
                        else:
                            raise NotImplementedError("Create additional mux to update dst value conditionally")
                        res.obj.name = name
                        valCache.add(mb, dst, res, True)
                    else:
                        constructor: HlsRead = ioNodeConstructors[srcIo][0]
                        if constructor is None:
                            raise AssertionError("The io without any read somehow requires read", srcIo, instr)
                        constructor._translateMirToNetlist(
                            constructor, self, syncTracker, mbSync, instr, srcIo, index, cond, dst)

                elif opc == TargetOpcode.HWTFPGA_CSTORE:
                    # store to data channel
                    srcVal, dstIo, index, cond = ops
                    constructor: HlsWrite = ioNodeConstructors[dstIo][1]
                    if constructor is None:
                        raise AssertionError("The io without any write somehow requires write", dstIo, instr)
                    constructor._translateMirToNetlist(
                        constructor, self, syncTracker, mbSync, instr, srcVal, dstIo, index, cond)

                elif opc == TargetOpcode.HWTFPGA_ICMP:
                    predicate, lhs, rhs = ops
                    opDef = self.CMP_PREDICATE_TO_OP[predicate]
                    res = builder.buildOp(opDef, BIT, lhs, rhs)
                    res.obj.name = name
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_EXTRACT:
                    src, offset, width = ops
                    if isinstance(offset, int):
                        if width == 1:
                            # to prefer more simple notation
                            index = INT.from_py(offset)
                        else:
                            index = SLICE.from_py(slice(offset + width, offset, -1))
                    else:
                        raise NotImplementedError()

                    res = builder.buildOp(AllOps.INDEX, Bits(width), src, index)
                    res.obj.name = name
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_MERGE_VALUES:
                    # src{N}, width{N} - lowest bits first
                    assert len(ops) % 2 == 0, ops
                    half = len(ops) // 2
                    res = builder.buildConcat(*ops[:half])
                    res.obj.name = name
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_GLOBAL_VALUE:
                    assert len(ops) == 1, ops
                    res = ops[0]
                    res.obj.name = name
                    valCache.add(mb, dst, res, True)

                elif opc == TargetOpcode.HWTFPGA_BR:
                    pass

                elif opc == TargetOpcode.HWTFPGA_BRCOND:
                    c = instr.getOperand(0)
                    assert c.isReg(), instr
                    translatedBranchConditions[c.getReg()] = syncTracker.resolveControlOutput(ops[0])

                elif opc == TargetOpcode.PseudoRET:
                    pass

                elif opc == TargetOpcode.IMPLICIT_DEF:
                    assert not ops, ops
                    BW = self.registerTypes[dst]
                    v = Bits(BW).from_py(None)
                    valCache.add(mb, dst, builder.buildConst(v), True)

                else:
                    raise NotImplementedError(instr)

    def _constructLiveInMuxesFromMeta(self,
                                      mb: MachineBasicBlock,
                                      liveInOrdered: List[Register],
                                      liveIns: Dict[Register, List[LiveInMuxMeta]],
                                      ):
        builder: HlsNetlistBuilder = self.builder
        valCache: MirToHwtHlsNetlistValueCache = self.valCache

        predCnt = mb.pred_size()
        for liveIn in liveInOrdered:
            liveIn: Register
            cases = liveIns[liveIn].values
            assert cases, ("MUX for liveIn has to have some cases (even if it is undef)", liveIn)
            if predCnt == 1:
                # this mux is just copy, no need to create actual HlsNetNodeMux
                assert len(cases) == 1, ("mb", mb.getNumber(), "liveIn", liveIn.virtRegIndex(), cases)
                v, _ = cases[0]
                if isinstance(v, HlsNetNodeOutLazy):
                    v = v.getLatestReplacement()
            else:
                assert len(cases) > 1, ("mb", mb.getNumber(), "liveIn", liveIn.virtRegIndex(), cases)
                dtype = Bits(self.registerTypes[liveIn])
                _operands = []
                for last, (src, cond) in iter_with_last(cases):
                    if isinstance(cond, HlsNetNodeOutLazy):
                        cond = cond.getLatestReplacement()
                    if isinstance(src, HlsNetNodeOutLazy):
                        src = src.getLatestReplacement()

                    _operands.append(src)
                    if not last:
                        # last case must be always satisfied because the block must have been entered somehow
                        _operands.append(cond)
                name = f"bb{mb.getNumber():d}_phi_r{liveIn.virtRegIndex():d}"
                v = builder.buildMux(dtype, tuple(_operands), name=name)

            valCache.add(mb, liveIn, v, False)

        for predMb in mb.predecessors():
            predMbSync = self.blockSync[predMb]
            sucMb = mb
            edgeMeta = self.edgeMeta[(predMb, sucMb)]
            if predMbSync.needsControl and edgeMeta.reuseDataAsControl is None:
                # construct channel for control
                v = None
                if edgeMeta.etype == MACHINE_EDGE_TYPE.BACKWARD:
                    v = self.builder.buildConst(HVoidData.from_py(None))
                    v = self._constructBackedgeBuffer("c", predMb, sucMb, (predMb, sucMb), v, isControl=True)
                    wn: HlsNetNodeWriteBackedge = v.obj.associatedWrite
                    if edgeMeta.inlineRstDataFromEdge is not None:
                        wn.channelInitValues = (tuple(),)
                    edgeMeta.loopChannelGroupAppendWrite(wn, True)

                elif edgeMeta.etype == MACHINE_EDGE_TYPE.FORWARD:
                    name = f"bb{predMb.getNumber()}_to_bb{sucMb.getNumber()}_c"
                    v = self.builder.buildConst(HVoidData.from_py(None))
                    wn, _, v = HlsNetNodeWriteForwardedge.createPredSucPair(self.netlist, name, v)
                    if edgeMeta.inlineRstDataFromEdge is not None:
                        raise NotImplementedError()
                    edgeMeta.loopChannelGroupAppendWrite(wn, True)

                if v is not None:
                    edgeMeta.buffers.append(((predMb, sucMb), v))

    def constructLiveInMuxes(self, mf: MachineFunction) -> BlockLiveInMuxSyncDict:
        """
        For each block for each live in register create a MUX which will select value of register for this block.
        (Or just propagate value from predecessor if there is just a single one)
        If the value comes from backedge create also a backedge buffer for it.
        """
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
        netlist: HlsNetlistCtx = self.netlist
        blockLiveInMuxInputSync: BlockLiveInMuxSyncDict = {}
        liveness = self.liveness

        # list of liveIn variables is used to process them in deterministic order
        liveInsForBlock: Dict[MachineBasicBlock,  # block where the liveInMux is constructed
                              Tuple[List[Register], Dict[Register, LiveInMuxMeta]]] = {}
        MRI = mf.getRegInfo()
        for mb in mf:
            liveInsForBlock[mb] = ([], {})

        for predMb in mf:
            predMb: MachineBasicBlock
            # Construct block input MUXes.
            # the liveIns are not required to be same because in some cases
            # the libeIn is used only by MUX input for a specific predecessor
            # First we collect all inputs for all variant then we build MUX.
            predLiveness = liveness[predMb]
            for sucMb in predMb.successors():
                sucMb: MachineBasicBlock
                edgeMeta: MachineEdgeMeta = self.edgeMeta[(predMb, sucMb)]
                liveInOrdered, liveIns = liveInsForBlock[sucMb]
                liveInOrdered: List[Register]
                liveIns: Dict[Register, List[LiveInMuxMeta]]

                for liveIn in predLiveness[sucMb]:
                    liveIn: Register
                    if not self._regIsValidLiveIn(MRI, liveIn):
                        continue

                    muxMeta = liveIns.get(liveIn, None)
                    if muxMeta is None:
                        # we step upon a new liveIn variable, we create a list for its values
                        liveInOrdered.append(liveIn)
                        muxMeta = liveIns[liveIn] = LiveInMuxMeta()

                    muxMeta: LiveInMuxMeta
                    dtype = Bits(self.registerTypes[liveIn])
                    v = valCache.get(predMb, liveIn, dtype)

                    wn = None
                    isReusedAsControl = edgeMeta.reuseDataAsControl and liveIn == edgeMeta.reuseDataAsControl
                    if edgeMeta.etype == MACHINE_EDGE_TYPE.BACKWARD:
                        name = f"r{liveIn.virtRegIndex():d}"
                        v = self._constructBackedgeBuffer(name, predMb, sucMb, (predMb, liveIn), v)
                        blockLiveInMuxInputSync[(predMb, sucMb, liveIn)] = v.obj
                        wn = v.obj.associatedWrite
                        edgeMeta.buffers.append((liveIn, v))
                        edgeMeta.loopChannelGroupAppendWrite(wn, isReusedAsControl)

                    elif edgeMeta.etype == MACHINE_EDGE_TYPE.FORWARD:
                        # rstPredeccessor are not resolve yet we generate this read-write pair but we may
                        # remove it later when rstPredeccessor extraction is possible
                        name = f"bb{predMb.getNumber()}_to_bb{sucMb.getNumber()}_r{liveIn.virtRegIndex():d}"
                        wn, rn, v = HlsNetNodeWriteForwardedge.createPredSucPair(netlist, name, v)
                        blockLiveInMuxInputSync[(predMb, sucMb, liveIn)] = rn
                        edgeMeta.buffers.append((liveIn, v))
                        edgeMeta.loopChannelGroupAppendWrite(wn, isReusedAsControl)

                    if wn is not None:
                        # write to channel only if the control flow will mobe to mb
                        brEn = valCache.get(predMb, BranchOutLabel(sucMb), BIT)
                        self._addExtraCond(wn, brEn, None)
                        self._addSkipWhen_n(wn, brEn, None)

                    c = valCache.get(sucMb, predMb, BIT)
                    muxMeta.values.append((v, c))

        for mb in mf:
            liveInsOrdered, liveIns = liveInsForBlock[mb]
            self._constructLiveInMuxesFromMeta(mb, liveInsOrdered, liveIns)

        return blockLiveInMuxInputSync

    # [todo] rm because it is handled when liveness dict is generated
    def _regIsValidLiveIn(self, MRI: MachineRegisterInfo, liveIn: Register):
        if liveIn in self.regToIo:
            return False  # we will use interface not the value of address where it is mapped
        if MRI.def_empty(liveIn):
            return False  # this is just form of undefined value (which is represented as constant)

        oneDef = MRI.getOneDef(liveIn)
        if oneDef is not None:
            defInstr = oneDef.getParent()
            if defInstr.getOpcode() in (TargetOpcode.HWTFPGA_GLOBAL_VALUE,
                                        TargetOpcode.HWTFPGA_ARG_GET,
                                        TargetOpcode.IMPLICIT_DEF):
                return False  # this is a pointer to a local memory which exists globally
        return True

    def updateThreadsOnLiveInMuxes(self, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        """
        Merge threads in  HlsNetlistAnalysisPassDataThreadsForBlocks to be as if the multiplexer on block inputs were constructed.
        """
        liveness = self.liveness
        MRI = self.mf.getRegInfo()
        for mb in self.mf:
            mb: MachineBasicBlock
            for pred in mb.predecessors():
                pred: MachineBasicBlock

                for liveIn in liveness[pred][mb]:
                    liveIn: Register
                    if not self._regIsValidLiveIn(MRI, liveIn):
                        continue

                    dtype = Bits(self.registerTypes[liveIn])
                    srcThread = self._getThreadOfReg(threads, pred, liveIn, dtype)
                    dstThread = self._getThreadOfReg(threads, mb, liveIn, dtype)
                    if srcThread is not None and dstThread is not None and srcThread is not dstThread:
                        threads.mergeThreads(srcThread, dstThread)

