from copy import copy
from itertools import chain
from typing import Tuple, Dict, List, Set, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT, SLICE, INT
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwtHls.frontend.ast.statementsRead import HlsRead
from hwtHls.frontend.ast.statementsWrite import HlsWrite
from hwtHls.frontend.hardBlock import HardBlockHwModule
from hwtHls.llvm.llvmIr import MachineRegisterInfo, MachineFunction, MachineBasicBlock, MachineLoop, Register, \
    MachineInstr, MachineOperand, CmpInst, TargetOpcode, HFloatTmpConfig
from hwtHls.netlist.analysis.blockSyncType import HlsNetlistAnalysisPassBlockSyncType
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.aggregatedLoop import HlsNetNodeAggregateLoop
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    HlsNetNodeOutAny
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.lowLevel import HlsNetlistAnalysisPassMirToNetlistLowLevel
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MACHINE_EDGE_TYPE
from hwtHls.ssa.translation.llvmMirToNetlist.utils import LiveInMuxMeta
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


BlockLiveInMuxSyncDict = Dict[Tuple[MachineBasicBlock, MachineBasicBlock, Register], HlsNetNodeExplicitSync]


def _getRtlAckOfNode(n: HlsNetNodeExplicitSync) -> Optional[HlsNetNodeOut]:
    if isinstance(n, HlsNetNodeRead):
        if n._rtlUseValid:
            return n.getValidNB()
    else:
        if n._rtlUseReady:
            return n.getReadyNB()
    return None


class HlsNetlistAnalysisPassMirToNetlistDatapath(HlsNetlistAnalysisPassMirToNetlistLowLevel):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist
    """

    def _translateRegToIoOrGlobalValue(self, MRI: MachineRegisterInfo,
                        instr: MachineInstr,
                        valCache: MirToHwtHlsNetlistValueCache,
                        mbMeta: MachineBasicBlockMeta,
                        builder: HlsNetlistBuilder, r: Register):
        io = self.regToIo.get(r, None)
        if io is not None:
            return io

        addrDefMO = MRI.getOneDef(r)
        assert addrDefMO is not None, instr
        addrDefInstr = addrDefMO.getParent()
        addrDefOpc = addrDefInstr.getOpcode()
        assert addrDefOpc == TargetOpcode.HWTFPGA_GLOBAL_VALUE
        op = valCache._toHlsCache[(addrDefInstr.getParent(), addrDefMO.getReg())]
        if op.obj.parent is not mbMeta.parentElement:
            k = (mbMeta.parentElement, addrDefInstr.getParent(), addrDefMO.getReg())
            _op = self._valueCopiedIntoElement.get(k)
            if _op is not None:
                op = _op
            elif isinstance(op.obj, HlsNetNodeConst):
                op = builder.buildConst(op.obj.val, name=op.obj.name)
                self._valueCopiedIntoElement[k] = op
            else:
                raise NotImplementedError(instr, op)
        return op

    def _translateDatapathInBlocksInstructions(self, MRI: MachineRegisterInfo, mbMeta: MachineBasicBlockMeta, mb: MachineBasicBlock):
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
        builder: HlsNetlistBuilder = mbMeta.parentElement.builder
        ioNodeConstructors = self.ioNodeConstructors
        allBlockingLoadAck: Optional[HlsNetNodeOutAny] = mbMeta.blockEn
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
                        op = self._translateRegToIoOrGlobalValue(MRI, instr, valCache, mbMeta, builder, r)
                        ops.append(op)
                    else:
                        isUndef = r not in self.regToIo and MRI.def_empty(r)
                        if not isUndef:
                            rDef = MRI.getOneDef(r)
                            isUndef = rDef is not None and rDef.getParent().getOpcode() == TargetOpcode.IMPLICIT_DEF

                        if isUndef:
                            bw = self.registerTypes[r]
                            op = builder.buildConst(HBits(bw).from_py(None))
                        else:
                            op = self._translateRegister(mb, r)
                        ops.append(op)

                elif mo.isMBB():
                    ops.append(self._translateMBB(mo.getMBB()))
                elif mo.isImm():
                    ops.append(mo.getImm())
                elif mo.isCImm():
                    ops.append(self._translateConstant(builder, mo.getCImm()))
                elif mo.isPredicate():
                    ops.append(CmpInst.Predicate(mo.getPredicate()))
                elif mo.isGlobal():
                    ops.append(self._translateGlobal(builder, mo.getGlobal()))
                else:
                    raise NotImplementedError(instr, mo)

            if dst is None:
                name = None
            else:
                name = f"bb{mb.getNumber()}_r{dst.virtRegIndex():d}"

            res = None
            opDef = self.OPC_TO_OP.get(opc, None)
            if opDef is not None:
                opSpecialization = None
                resT = ops[0]._dtype
                if opc in self._FP_BIN_OPCODES:
                    hFloatTmpConfigMembers = ops[-HFloatTmpConfig.MEMBER_CNT:]
                    opSpecialization = HFloatTmpConfig(*hFloatTmpConfigMembers)
                    ops = ops[:-HFloatTmpConfig.MEMBER_CNT]
                elif opc in self._BITCOUNT_OPCODES:
                    resT = HBits(log2ceil(resT.bit_length() + 1))

                res = builder.buildOp(opDef, opSpecialization, resT, *ops, name=name)
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

                    res = builder.buildMux(resT, tuple(ops), name=name)
                    valCache.add(mb, dst, res, True)

            elif opc == TargetOpcode.HWTFPGA_CLOAD:
                # load from data channel
                srcIo, index, cond = ops  # [todo] implicit operands
                if isinstance(srcIo, HlsNetNodeOut):
                    # this would be rom load implemented as INDEX operator
                    res = builder.buildOp(HwtOps.INDEX, None, srcIo._dtype.element_t, srcIo, index, name=name)
                    if isinstance(cond, int):
                        assert cond == 1, instr
                        # always enabled, no additional care is needed
                    else:
                        # Create additional mux to update dst value conditionally
                        res = builder.buildMux(res._dtype, (res, cond, builder.buildConstPy(res._dtype, None)), name=name)

                    valCache.add(mb, dst, res, True)
                else:
                    # this is form of load instruction which is delegated to constructor
                    # which was inferred from IO type on SSA construction
                    constructor: HlsRead = ioNodeConstructors[srcIo][0]
                    if constructor is None:
                        raise AssertionError("The io without any read somehow requires read", srcIo, instr)
                    if isinstance(cond, int):
                        assert cond == 1, instr
                        cond = None
                    _cond = builder.buildAndOptional(allBlockingLoadAck, cond)
                    nodes = constructor._translateMirToNetlist(
                        constructor, self, mbMeta, instr, srcIo, index, _cond, dst)
                    if constructor._isBlocking:
                        lastAddedNodeAck = _getRtlAckOfNode(nodes[-1])
                        _allLoadAck = builder.buildAndOptional(_cond, lastAddedNodeAck,
                                                       name=f"allLoadAck_n{nodes[-1]._id}" if cond is None else None)
                        if cond is None:
                            allBlockingLoadAck = _allLoadAck
                        else:
                            allBlockingLoadAck = builder.buildOr(
                                _allLoadAck,
                                (builder.buildAnd(allBlockingLoadAck, builder.buildNot(cond))), f"allLoadAck_n{nodes[-1]._id}")

            elif opc == TargetOpcode.HWTFPGA_CSTORE:
                # store to data channel
                srcVal, dstIo, index, cond = ops
                constructor: HlsWrite = ioNodeConstructors[dstIo][1]
                if isinstance(cond, int):
                    assert cond == 1, instr
                    cond = None
                if constructor is None:
                    raise AssertionError("The io without any write somehow requires write", dstIo, instr)
                _cond = builder.buildAndOptional(allBlockingLoadAck, cond)
                constructor._translateMirToNetlist(
                    constructor, self, mbMeta, instr, srcVal, dstIo, index, _cond)

            elif opc == TargetOpcode.HWTFPGA_ICMP:
                predicate, lhs, rhs = ops
                opDef = self.CMP_PREDICATE_TO_OP[predicate]
                res = builder.buildOp(opDef, None, BIT, lhs, rhs)
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

                res = builder.buildOp(HwtOps.INDEX, None, HBits(width), src, index)
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
                mbMeta.translatedBranchConditions[c.getReg()] = builder.buildAndOptional(allBlockingLoadAck, ops[0])  # mbMeta.syncTracker.resolveControlOutput(ops[0])

            elif opc == TargetOpcode.HWTFPGA_RET:
                pass

            elif opc == TargetOpcode.IMPLICIT_DEF:
                assert not ops, ops
                BW = self.registerTypes[dst]
                v = HBits(BW).from_py(None)
                valCache.add(mb, dst, builder.buildConst(v), True)
            elif opc in (TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER,
                         TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE,
                         TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_WITH_SIDEEFFECT,
                         TargetOpcode.HWTFPGA_PYOBJECT_PLACEHOLDER_NOTDUPLICABLE_WITH_SIDEEFECT):
                objId = ops[0]
                try:
                    obj: HardBlockHwModule = self.placeholderObjectSlots[objId]
                except IndexError:
                    raise IndexError("ThMissing object requested by placeholder object id", objId, instr)
                inputs = ops[2:2 + (len(ops) - 2) // 2]
                obj.translateMirToNetlist(self, mbMeta, instr, builder, inputs, name)
            else:
                raise NotImplementedError(instr)

    def _collectBlocksForElement(self, mb: MachineBasicBlock):
        """
        bi-directionally collect all successors reachable trough NORMAL and RESET edges
        """
        found: SetList[MachineBasicBlock] = SetList()
        worklist: List[MachineBasicBlock] = [mb]
        edgeMeta = self.edgeMeta
        SUPPORTED_EDGES = (
            MACHINE_EDGE_TYPE.NORMAL,
            MACHINE_EDGE_TYPE.RESET
        )
        while worklist:
            mb: MachineBasicBlock = worklist.pop()
            if found.append(mb):
                # if it is not already added
                for otherMb, edge in chain(
                    ((otherMb, (otherMb, mb)) for otherMb in mb.predecessors()),
                    ((otherMb, (mb, otherMb)) for otherMb in mb.successors())
                    ):
                    eMeta: MachineEdgeMeta = edgeMeta[edge]
                    if eMeta.etype in SUPPORTED_EDGES:
                        worklist.append(otherMb)
        return found

    def _constructParentElemenForLoop(self, netlist:HlsNetlistCtx,
                                      loopElements: Dict[MachineBasicBlock, HlsNetNodeAggregateLoop],
                                      loop: MachineLoop,
                                      ):
        headerMb = loop.getHeader()
        existingLoopElm = loopElements.get(headerMb, None)
        # :note: headerMbMeta.parentElement may be ArchElement for begin part of the loop, thus we can not use it
        if existingLoopElm is not None:
            return existingLoopElm

        pLoop = loop.getParentLoop()
        if pLoop is None:
            parent = netlist
        else:
            parent = self._constructParentElemenForLoop(netlist, loopElements, pLoop)

        headerMbMeta:MachineBasicBlockMeta = self.blockMeta[headerMb]
        if headerMbMeta.isLoopHeaderOfFreeRunning:
            # parent loop was just found out to be without HW representation
            loopElm = parent
            loopElements[headerMb] = parent
            if self.dbgTracer:
                self.dbgTracer.log(("parent element for loop", str(loop), "use parent", parent))
        else:
            loopElm = HlsNetNodeAggregateLoop(netlist, SetList(), f"loop{headerMb.getNumber():d}")
            loopElements[headerMb] = loopElm
            parent.addNode(loopElm)
            if self.dbgTracer:
                self.dbgTracer.log(("parent element for loop", str(loop), "new", loopElm._id))

        if loopElm is not netlist:
            headerMbMeta.assignParentElement(loopElm)

        for mb in loop.getBlocks():
            if mb == headerMb:
                continue  # already resolved

            mbLoop = self.loops.getLoopFor(mb)
            if mbLoop != loop and mbLoop.getLoopDepth() > loop.getLoopDepth():
                # if mb is in some child loop
                # :note: loops can be interwired together in a way which that child of the child may be a parent, e.g:
                #   entry-> 1
                #   1 -> 1, 2
                #   2 -> 2, 1
                self._constructParentElemenForLoop(netlist, loopElements, mbLoop)
            elif loopElm is not netlist:
                mbMeta:MachineBasicBlockMeta = self.blockMeta[mb]
                mbMeta.assignParentElement(loopElm)

        return loopElm

    def _constructParentElementForBlock(self, netlist:HlsNetlistCtx,
                                        resolved: Set[MachineBasicBlock],
                                        loopElements: Dict[MachineBasicBlock, HlsNetNodeAggregateLoop],
                                        mb: MachineBasicBlock,
                                        violatesResourceConstraints:bool):
        """
        The MachineLoop may contain multiple ArchElements and ArchElement may contain multiple MachineLoop
        but MachineLoop or ArchElement must have a single parent (e.g. if loop span over multiple ArchElements
        they are children of this loop and contains only blocks of this loop)
        :note: mf iterator does not follow CFG, thus loop mb may not be a loop header when loop is visited first time
        :note: :class:`ArchElemnt` instances are never nested in each other, :class:`HlsNetNodeAggregateLoop` can
            be nested and may contain multiple :class:`ArchElemnt` instances
        :note: main purpose of HlsNetNodeAggregateLoop is to aggregate loop nodes for scheduling to have back tracking scope
        """
        if mb in resolved:
            return
        isResetBlock = False
        if mb.succ_size() == 1:
            suc = next(mb.successors())
            sucEdge: MachineEdgeMeta = self.edgeMeta[(mb, suc)]
            if sucEdge.etype == MACHINE_EDGE_TYPE.RESET:
                isResetBlock = True
        else:
            suc = None

        innerMostLoop: MachineLoop = self.loops.getLoopFor(suc if isResetBlock else mb)
        elementBlocks = self._collectBlocksForElement(mb)
        # for _mb in elementBlocks:
        #    _mbLoop = self.loops.getLoopFor(_mb)
        #    assert _mbLoop == innerMostLoop, (_mb, _mbLoop, innerMostLoop) # :note: may not be in the same loop if loop has isLoopHeaderOfFreeRunning (is discarded)

        if innerMostLoop is not None:
            # assert all parent loops are constructed
            parent = self._constructParentElemenForLoop(netlist, loopElements, innerMostLoop)
        else:
            parent = netlist
        # elementBlocks may contain only part of the loop or whole loop
        # * If it is only a part top parent will be loop and child ArchElements will be inside
        # * if it is whole loop ArchElement will be parent and the loop will be inside

        if violatesResourceConstraints:
            parentElement = ArchElementFsm(netlist, netlist.label, netlist.namePrefix)
            if self.dbgTracer:
                self.dbgTracer.log(("parent element for block ", mb.getNumber(), "new FSM:", parentElement._id))
        else:
            parentElement = ArchElementPipeline(netlist, netlist.label, netlist.namePrefix)
            if self.dbgTracer:
                self.dbgTracer.log(("parent element for block", mb.getNumber(), "new pipeline", parentElement._id))
        parent.addNode(parentElement)

        blockMeta = self.blockMeta
        for elmMb in elementBlocks:
            mbMeta: MachineBasicBlockMeta = blockMeta[elmMb]
            mbMeta.assignParentElement(parentElement)

        resolved.update(elementBlocks)

    def _constructParentElement(self, mf: MachineFunction):
        """
        Analyze resource constraints to decide if we should start with ArchElementPipeline or if there is some constraint and
        circuit must start from ArchElementFsm
        :note: 1 MF should represent just 1 ArchElement.
        It is desired to cut function to threads on MIR level, but ArchElement can be also cut later
        (but the analysis is significantly more complex and is done after scheduling).
        """
        constraints: SchedulingResourceConstraints = self.netlist.scheduler.resourceUsage.resourceConstraints
        # if it is in format of:
        # resetBlock (loopHeaderOfFreeRunning)*
        resourcesAvailable = copy(constraints)
        MRI = mf.getRegInfo()
        violatesResourceConstraints = False
        for mb in mf:
            mb: MachineBasicBlock
            # mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
            for instr in mb:
                res = self._getSchedulingResourceForInstruction(MRI, instr)
                if res is not None:
                    curAvailable = resourcesAvailable.get(res, None)
                    if curAvailable is not None:
                        if curAvailable == 0:
                            violatesResourceConstraints = True
                            break
                        curAvailable -= 1
                        resourcesAvailable[res] = curAvailable

        netlist = self.netlist
        resolved: Set[MachineBasicBlock] = set()
        loopElements: Dict[MachineBasicBlock, HlsNetNodeAggregateLoop] = {}

        for mb in mf:
            mb: MachineBasicBlock
            self._constructParentElementForBlock(
                netlist, resolved, loopElements, mb, violatesResourceConstraints)

    def translateDatapathInBlocks(self, mf: MachineFunction):
        """
        Translate all non control instructions which are entirely in some block.
        (Excluding connections between blocks)
        """
        self.netlist.getAnalysis(HlsNetlistAnalysisPassBlockSyncType)
        MRI = mf.getRegInfo()
        # valCache: MirToHwtHlsNetlistValueCache = self.valCache
        if self.dbgTracer:
            with self.dbgTracer.scoped("_constructParentElement", mf.getName().str()):
                self._constructParentElement(mf)
        else:
            self._constructParentElement(mf)

        for mb in mf:
            mb: MachineBasicBlock
            mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
            # construct lazy output for liveIns in advance to assert that we have lazy input to replace later
            # with a liveIn mux
            # seenLiveIns: Set[Register] = set()
            # #blockBoudary = mbMeta.syncTracker.blockBoudary
            # for pred in mb.predecessors():
            #    for liveIn in sorted(self.liveness[pred][mb], key=lambda li: li.virtRegIndex()):
            #        if self._regIsValidLiveIn(MRI, liveIn) and liveIn not in seenLiveIns:
            #            #dtype = HBits(self.registerTypes[liveIn])
            #            #liveInO = valCache.get(mb, liveIn, dtype)
            #            #blockBoudary.add(liveInO)
            #            seenLiveIns.add(liveIn)
            self._translateDatapathInBlocksInstructions(MRI, mbMeta, mb)

    def _constructLiveInMuxesFromMeta(self,
                                      mb: MachineBasicBlock,
                                      liveInOrdered: List[Register],
                                      liveIns: Dict[Register, List[LiveInMuxMeta]],
                                      ):
        mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
        builder: HlsNetlistBuilder = mbMeta.parentElement.builder
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
                dtype = HBits(self.registerTypes[liveIn])
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
                # optimization is disabled because MUX is potentially needed for ResetValueExtractor
                v = builder.buildMux(dtype, tuple(_operands), opt=False, name=name)

            valCache.add(mb, liveIn, v, False)

    def _constructControlChannelsFromMeta(self, mb: MachineBasicBlock):
        # construct control channels
        for predMb in mb.predecessors():
            sucMb = mb
            edgeMeta = self.edgeMeta[(predMb, sucMb)]

            if edgeMeta.reuseDataAsControl is None:
                # construct channel for control
                isBackedge = edgeMeta.etype == MACHINE_EDGE_TYPE.BACKWARD
                if isBackedge or edgeMeta.etype == MACHINE_EDGE_TYPE.FORWARD:
                    v = HVoidData.from_py(None)
                    # :note: all other writes should be constructed so c write is
                    # asserted to be the last
                    v = self._constructBuffer("c", predMb, sucMb, (predMb, sucMb), v,
                                              isBackedge=isBackedge, isControl=True)
                    if edgeMeta.inlineRstDataFromEdge is not None:
                        v.obj.channelInitValues = (tuple(),)
                    wn: HlsNetNodeWriteBackedge = v.obj.associatedWrite
                    edgeMeta.loopChannelGroupAppendWrite(wn, True)
                    edgeMeta.buffers.append(((predMb, sucMb), v))

    def constructLiveInMuxes(self, mf: MachineFunction) -> BlockLiveInMuxSyncDict:
        """
        For each block for each live in register create a MUX which will select value of register for this block.
        (Or just propagate value from predecessor if there is just a single one)
        If the value comes from backedge create also a backedge buffer for it.
        """
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
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
            predMbMeta = self.blockMeta[predMb]
            constLiveOuts = predMbMeta.constLiveOuts
            with self.dbgTracer.scoped(HlsNetlistAnalysisPassMirToNetlistDatapath.constructLiveInMuxes, predMb.getNumber()):
                for sucMb in predMb.successors():
                    sucMb: MachineBasicBlock
                    edgeMeta: MachineEdgeMeta = self.edgeMeta[(predMb, sucMb)]
                    liveInOrdered, liveIns = liveInsForBlock[sucMb]
                    liveInOrdered: List[Register]
                    liveIns: Dict[Register, List[LiveInMuxMeta]]
                    with self.dbgTracer.scoped("suc", sucMb.getNumber()):
                        sucMbMeta = self.blockMeta[sucMb]
                        writeListForOrdering: List[HlsNetNodeWrite] = []
                        isBackedge = edgeMeta.etype == MACHINE_EDGE_TYPE.BACKWARD
                        isEdgeWithChannels = edgeMeta.etype in (MACHINE_EDGE_TYPE.BACKWARD,
                                                                MACHINE_EDGE_TYPE.FORWARD)
                        mayPropagateConstants = edgeMeta.inlineRstDataFromEdge is None
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
                            dtype = HBits(self.registerTypes[liveIn])
                            v = valCache.get(predMb, liveIn, dtype)

                            isReusedAsControl = edgeMeta.reuseDataAsControl and liveIn == edgeMeta.reuseDataAsControl
                            if isEdgeWithChannels:
                                if mayPropagateConstants and liveIn in constLiveOuts:
                                    assert isinstance(v.obj, HlsNetNodeConst), v
                                    if predMbMeta.parentElement is not sucMbMeta.parentElement:
                                        # copy const to successor element
                                        v = sucMbMeta.parentElement.builder.buildConst(v.obj.val)
                                else:
                                    v = self._constructBuffer(
                                        f"r{liveIn.virtRegIndex():d}", predMb, sucMb, (predMb, liveIn), v,
                                        isBackedge=isBackedge,
                                        addWriteToOrderingChain=not isBackedge)
                                    rn = v.obj
                                    wn = v.obj.associatedWrite
                                    if isBackedge:
                                        writeListForOrdering.append(wn)

                                    self.dbgTracer.log(("adding channel, ", wn))
                                    blockLiveInMuxInputSync[(predMb, sucMb, liveIn)] = rn

                                    edgeMeta.buffers.append((liveIn, v))
                                    edgeMeta.loopChannelGroupAppendWrite(wn, isReusedAsControl)
                                    # write to channel only if the control flow will move to mb
                                    brEn = valCache.get(predMb, BranchOutLabel(sucMb), BIT)
                                    self._addExtraCond(wn, brEn, None)
                                    self._addSkipWhen_n(wn, brEn, None)

                            c = valCache.get(sucMb, predMb, BIT)  # get flag for sucMb is entered from predMb
                            muxMeta.values.append((v, c))

                        if isBackedge:
                            # it must be reversed in order to prevent deadlocks
                            # and to assert that the data channel used for control is writen as last
                            for wn in reversed(writeListForOrdering):
                                predMbMeta.addOrderedNode(wn)
        for mb in mf:
            liveInsOrdered, liveIns = liveInsForBlock[mb]
            self._constructLiveInMuxesFromMeta(mb, liveInsOrdered, liveIns)
            self._constructControlChannelsFromMeta(mb)

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

