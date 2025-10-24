from copy import copy
from typing import List, Dict, Optional, Tuple, Set, Sequence

from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoopInfo, \
    MachineLoop, MachineInstr, Register, TargetOpcode, MachineFunction, MachineRegisterInfo, MachineOperand
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy
from hwtHls.netlist.scheduler.resourceList import SchedulingResourceConstraints, \
    SchedulingResourceType
from hwtHls.platform.opRealizationMeta import ComponentRealizationMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import \
    MachineEdgeMeta, MachineEdge, MACHINE_EDGE_TYPE, MachineLoopId
from hwtHls.ssa.translation.llvmMirToNetlist.utils import _regIsValidLiveIn
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from ipCorePackager.constants import DIRECTION


class HlsNetlistAnalysisPassBlockSyncType(HlsNetlistAnalysisPass):
    '''
    This pass updates blockMeta dictionary in :class:`hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist` with
    flags which are describing what type of synchronization for block/block edge should be used.

    :note: This is thread level synchronization of control flow in blocks not RTL type of synchronization.
        That means this does not solve synchronization of pipeline stages but
        it must solve the synchronization between accesses to exclusive resources.
    
    :attention: This algorithm expects optimized code (after if-conversion, branch folding)
        and does not check for trivial cases removed by mentioned passes.
    
    .. code-block:: llvm

        entry: #
            %0 = G_CONSTANT 0
            G_BR while
        while: # isCycleEntryPoint, rstPredecessor=entry
            # %0 later resolved as a register with a 0 as reset value
            use(%0)
            %0 = G_CONSTANT 1
            G_BR while

    In this case the synchronization is not needed because body contains
    a single thread and PHIs can be reduced using reset value extraction.

    .. code-block:: llvm

        entry: #
            G_BR label bb0
        bb0: # isCycleEntryPoint, needsControl, rstPredecessor=entry
            %0 = G_CONSTANT 0
            G_BR label while1
        while1: # isCycleEntryPoint, needsControl
            use(%0)
            %1 = read()
            %0 = G_CONSTANT 1
            G_BRCOND %1, bb0, while1

    In this case loop in while1 needs synchronization because bb0 is not rstPredecessor or while1.

    :note: This is called upon once the datapath in blocks is resolved.
        This is because we need to know HlsNetlistAnalysisPassDataThreadsForBlocks
        and it can be only obtained once datapath in blocks was constructed.
        :see: :class:`~.HlsNetlistAnalysisPassDataThreadsForBlocks`
    '''
    _CONSTANT_OPCODES = {
        TargetOpcode.G_CONSTANT,
        TargetOpcode.HWTFPGA_BR,
        TargetOpcode.HWTFPGA_ARG_GET,
        TargetOpcode.HWTFPGA_GLOBAL_VALUE,
        TargetOpcode.HWTFPGA_IMPLICIT_DEF
    }

    @classmethod
    def _blockCanBeInlinedAsReset(cls, mb: MachineBasicBlock):
        defsSeen: set[Register] = set()
        for mi in mb:
            mi: MachineInstr
            opc = mi.getOpcode()
            for op in mi.operands():
                op: MachineOperand
                if op.isReg() and op.isDef():
                    defsSeen.add(op.getReg())

            if opc not in cls._CONSTANT_OPCODES:
                if opc == TargetOpcode.HWTFPGA_MUX and mi.getNumOperands() == 2:
                    # constant defined as copy of constant using HWTFPGA_MUX instr
                    continue
                elif opc == TargetOpcode.HWTFPGA_MERGE_VALUES:
                    for op in mi.operands():
                        if op.isReg() and not op.isDef():
                            if op.getReg() not in defsSeen:
                                return False
                    continue  # just merge of constants

                return False

        return True

    def _resolveRstPredecessor(self, mb: MachineBasicBlock,
                               mbMeta: MachineBasicBlockMeta,
                               loop: MachineLoop) -> Optional[MachineBasicBlock]:
        if loop.getHeader() != mb:
            # can not extract reset if this not a top loop
            return mbMeta.rstPredeccessor

        topLoop = loop
        while True:
            p = topLoop.getParentLoop()
            if p is None or p.getHeader() != mb:
                break
            topLoop = p

        if mbMeta.rstPredeccessor is None and mb.pred_size() >= 2:
            # check if some predecessor is bb0 and check if all other predecessors are reenter from the loop which has this block as header
            p0 = None
            mostOuterOuterPred = None
            for pred in mb.predecessors():
                # one of predecessors may possibly be suitable for reset extraction
                if pred.pred_size() == 0 and self._blockCanBeInlinedAsReset(pred):
                    if p0 is not None:
                        # there are multiple enters from bb0 we can not extract and this should be already optimized away
                        return None
                    p0 = pred

                elif not topLoop.containsBlock(pred):
                    # can not extract because this in not top loop
                    return None

                else:
                    mostOuterOuterPred = pred

            if p0 is None:
                # Can not find rst predecessor to inline for mb
                return None

            assert mostOuterOuterPred is not None, ("Can not find block where to inline initialization for rst block for", mb)

            mbMeta.rstPredeccessor = p0
            if mbMeta.fsm is not None:
                p0Meta = self.blockMeta[p0]
                assert p0Meta.fsm is None, p0
                mbMeta.fsm.append(p0)
                p0Meta.fsm = mbMeta.fsm

            rstE: MachineEdgeMeta = self.edgeMeta[(p0, mb)]
            rstE.etype = MACHINE_EDGE_TYPE.RESET
            rstE.inlineRstDataToEdge = (mostOuterOuterPred, mb)
            rstReplaceEdge: MachineEdgeMeta = self.edgeMeta[rstE.inlineRstDataToEdge]
            assert rstReplaceEdge.etype != MACHINE_EDGE_TYPE.DISCARDED, (rstE, rstReplaceEdge)
            rstReplaceEdge.inlineRstDataFromEdge = (p0, mb)

        return mbMeta.rstPredeccessor

    def _tryToFindRegWhichCanBeUsedAsControl(self, mir: "HlsNetlistAnalysisPassMirToNetlist",
                                             MRI: MachineRegisterInfo,
                                             pred: MachineBasicBlock, mb: MachineBasicBlock,
                                             eMeta: MachineEdgeMeta) -> Optional[Register]:
        assert eMeta.srcBlock == pred and eMeta.dstBlock == mb, (eMeta, pred, mb)
        if eMeta.reuseDataAsControl is not None:
            return eMeta.reuseDataAsControl
        constLiveouts = self.blockMeta[pred].constLiveOuts
        for liveIn in mir.liveness[pred][mb]:
            # [todo] prefer using same liveIns from every predecessor
            # [todo] prefer using variables which are used the most early
            if liveIn not in constLiveouts and _regIsValidLiveIn(mir.regToIo, MRI, liveIn):
                eMeta.reuseDataAsControl = liveIn
                return liveIn

        return None

    def _resolveUsedLoops(self, mb: MachineBasicBlock, mbMeta: MachineBasicBlockMeta, loop: MachineLoop):
        mir = self.originalMir
        MRI = mir.mf.getRegInfo()
        assert loop.getHeader() == mb, (mb, loop)
        edgeMeta: MachineEdgeMeta = self.edgeMeta
        topLoop = loop
        mbMeta.isLoopHeader = True
        while True:
            depth = loop.getLoopDepth()
            loopId = MachineLoopId(mb.getNumber(), depth)
            for pred in mb.predecessors():
                e = (pred, mb)
                em: MachineEdgeMeta = edgeMeta[e]
                if loop.containsBlock(pred):
                    # reenter
                    em.reenteringLoops.append(loopId)
                else:
                    # enter
                    em.enteringLoops.append(loopId)
                    self._makeNormalEdgeForward(MRI, em)

            exitBlocks = tuple(loop.getUniqueExitBlocks())
            exitBlocksSet = set(exitBlocks)
            hasDedicatedExits = True
            if not loop.hasDedicatedExits():
                for e in exitBlocks:
                    e: MachineBasicBlock
                    for pred in e.predecessors():
                        if not loop.containsBlock(pred) and pred not in exitBlocksSet:
                            hasDedicatedExits = False
                            break
                    if not hasDedicatedExits:
                        break

            if hasDedicatedExits:
                # make all jumps from exit blocks a forward or backward edge
                for eBlock in exitBlocks:
                    for suc in eBlock.successors():
                        em: MachineEdgeMeta = edgeMeta[(eBlock, suc)]
                        if suc not in exitBlocksSet:
                            em.exitingLoops.append(loopId)
                            self._makeNormalEdgeForward(MRI, em)

            else:
                # make all jumps from loop forward edge
                for e in loop.getExitEdges():
                    em: MachineEdgeMeta = edgeMeta[e]
                    em.exitingLoops.append(loopId)
                    self._makeNormalEdgeForward(MRI, em)

            p = topLoop.getParentLoop()
            if p is None or p.getHeader() != mb:
                break

    def _makeNormalEdgeForward(self, MRI: MachineRegisterInfo, em: MachineEdgeMeta) -> bool:
        if em.etype == MACHINE_EDGE_TYPE.NORMAL:
            em.etype = MACHINE_EDGE_TYPE.FORWARD
            self._tryToFindRegWhichCanBeUsedAsControl(self.originalMir, MRI, em.srcBlock, em.dstBlock, em)
            return True
        else:
            return False

    # def _hasSomeLiveInFromEveryPredec(self, mb: MachineBasicBlock):
    #    mir = self.originalMir
    #    MF = mir.mf
    #    liveness = mir.liveness
    #    MRI = MF.getRegInfo()
    #    if mb.pred_size() == 0:
    #        return False
    #
    #    for pred in mb.predecessors():
    #        liveInGroup = liveness[pred][mb]
    #        someLiveInFound = False
    #        for liveIn in liveInGroup:
    #            if _regIsValidLiveIn(mir.regToIo, MRI, liveIn):
    #                someLiveInFound = True
    #                break
    #        if not someLiveInFound:
    #            return False
    #
    #    return True

    def _resolveBlockMeta(self, mb: MachineBasicBlock):
        """
        The code needs a synchronization if it starts a new thread without data dependencies and has predecessor thread.

        :note: The synchronization is always marked for the start of the thread.
        """
        # resolve control enable flag for a block
        mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
        loops: MachineLoopInfo = self.loops
        needsControlOld = mbMeta.needsControl
        if not needsControlOld:
            componentGenerators = self.platform._componentGenerators
            MRI = mb.getParent().getRegInfo()
            netlist = self.netlist
            for mi in mb:
                mi: MachineInstr
                opc = mi.getOpcode()
                cgen = componentGenerators.get(opc)
                if cgen is not None:
                    cgen: ComponentGenerator
                    r: ComponentRealizationMeta = cgen.resolveRealizationOfLlvmMirMachineInstr(MRI, netlist, mi)
                    assert isinstance(r, ComponentRealizationMeta), (mi, cgen, r)
                    if not r.canBeSynchornizedPurelyByLatency():
                        mbMeta.needsControl = True
                        break

        if mb.pred_size() == 0 and mb.succ_size() == 0:
            assert next(iter(self.originalMir.mf)) == mb, "No predecessor is allowed only for entry block"
            mbMeta.needsControl = True
            mbMeta.needsStarter = True
        elif self.loops.isLoopHeader(mb):
            loop: MachineLoop = loops.getLoopFor(mb)
            # The synchronization is not required if it could be only by the data itself.
            # It can be done by data itself if there is an single output/write which has all
            # input as transitive dependencies (unconditionally.) And if this is an infinite cycle.
            # So we do not need to check the number of executions.
            self._resolveRstPredecessor(mb, mbMeta, loop)
            self._resolveUsedLoops(mb, mbMeta, loop)

            if not mbMeta.needsControl:
                if (
                      (mb.pred_size() > 1 and
                       (mb.pred_size() != 2 or not mbMeta.rstPredeccessor)  # and
                        # not self._hasSomeLiveInFromEveryPredec(mb)
                       )
                      ):
                    # check for multiple independent threads in body or more entry points to a loop
                    loopBodySelfSynchronized = True
                    for pred in mb.predecessors():
                        pred: MachineBasicBlock
                        isLoopReenter = loop.containsBlock(pred)
                        # reenter does not need explicit sync because it is synced by data
                        # rstPredeccessor does not need explicit sync because it will be inlined to reset values
                        if not isLoopReenter and mbMeta.rstPredeccessor is not pred:
                            loopBodySelfSynchronized = False
                            break

                    if loopBodySelfSynchronized and mb.pred_size() == 2:
                        pass
                    else:
                        mbMeta.needsControl = True

                else:
                    mbMeta.needsControl = True

        elif not mbMeta.needsControl:
            needsControl = False
            if (any(self.blockMeta[pred].needsControl for pred in mb.predecessors()) or
                any(self.blockMeta[suc].needsControl for suc in mb.successors())
                ):
                needsControl = True
            elif (mbMeta.needsStarter and
                      (mb.succ_size() == 0 or
                       any(loops.getLoopFor(suc) is None for suc in mb.successors()))):
                needsControl = True

            mbMeta.needsControl = needsControl

        if not needsControlOld and mbMeta.needsControl:
            self._onBlockNeedsControl(mb)

    def _onBlockNeedsControl(self, mb: MachineBasicBlock):
        blockMeta = self.blockMeta
        mbMeta: MachineBasicBlockMeta = blockMeta[mb]
        rstPred = mbMeta.rstPredeccessor
        allRstLiveInsInlinable = True
        if rstPred is not None:
            rstPred: MachineBasicBlock
            if rstPred.pred_size():
                allRstLiveInsInlinable = False
            else:
                for inst in rstPred:
                    inst: MachineInstr
                    opc = inst.getOpcode()
                    if opc != TargetOpcode.HWTFPGA_BR:
                        if opc == TargetOpcode.HWTFPGA_MUX and inst.getNumOperands() == 2:  # just copy
                            continue
                        allRstLiveInsInlinable = False
                        break

        mir = self.originalMir
        MRI = mir.mf.getRegInfo()
        loop: MachineLoop = self.loops.getLoopFor(mb)
        if loop is not None and loop.getHeader() != mb:
            loop = None

        for pred in mb.predecessors():
            if allRstLiveInsInlinable and pred is rstPred:
                continue

            predMbMeta: MachineBasicBlockMeta = blockMeta[pred]
            # canUseDataAsControl = False
            eMeta: MachineEdgeMeta = self.edgeMeta[(pred, mb)]
            if loop is not None or (pred, mb) in self.backedges or eMeta.etype == MACHINE_EDGE_TYPE.FORWARD:
                # canUseDataAsControl =  is not None
                self._tryToFindRegWhichCanBeUsedAsControl(mir, MRI, pred, mb, eMeta)

            if eMeta.etype != MACHINE_EDGE_TYPE.RESET and not predMbMeta.needsControl:  # not canUseDataAsControl and
                predMbMeta.needsControl = True
                if not predMbMeta.needsStarter and not pred.pred_size():
                    predMbMeta.needsStarter = True

                self._onBlockNeedsControl(pred)

        for suc in mb.successors():
            mbMeta: MachineBasicBlockMeta = blockMeta[suc]
            if not mbMeta.needsControl:
                mbMeta.needsControl = True
                self._onBlockNeedsControl(suc)

    def _collectBlockNeighbors(self, mb: MachineBasicBlock, branchDirection: DIRECTION,
                              predecessors: SetList[MachineBasicBlock],
                              successors: SetList[MachineBasicBlock]):
        """
        Collect all successors of all predecessors or all predecessors of all successors recursively
        
        .. figure:: _static/blockNeighbors.png
            
            predecessors - 0,1,2,3
            successors - 3,4,5
        
        """
        if branchDirection == DIRECTION.IN:
            if not successors.append(mb):
                return
            for pred in mb.predecessors():
                self._collectBlockNeighbors(pred, DIRECTION.OUT, predecessors, successors)
        else:
            assert branchDirection == DIRECTION.OUT
            if not predecessors.append(mb):
                return
            for suc in mb.successors():
                self._collectBlockNeighbors(suc, DIRECTION.IN, predecessors, successors)

    @staticmethod
    def _initBlockMeta(mf: MachineFunction,
                           netlist: HlsNetlistCtx,
                           valCache: MirToHwtHlsNetlistValueCache,
                           blockMeta:Dict[MachineBasicBlock, MachineBasicBlockMeta],
                           blockFsms: dict[MachineBasicBlock, SetList[MachineBasicBlock]]):
        for mb in mf:
            mb: MachineBasicBlock

            constLiveOuts: Set[Register] = set()
            for instr in mb:
                instr: MachineInstr
                isConstDef = \
                    instr.getOpcode() == TargetOpcode.HWTFPGA_MUX and\
                    instr.getNumOperands() == 2 and\
                    instr.getOperand(1).isCImm()
                if isConstDef:
                    constLiveOuts.add(instr.getOperand(0).getReg())
                else:
                    for op in instr.operands():
                        if op.isReg() and op.isDef():
                            constLiveOuts.discard(op.getReg())

            mbMeta = MachineBasicBlockMeta(
                mb,
                constLiveOuts,
                HlsNetNodeOutLazy(netlist, [], valCache, BIT, name=f"bb{mb.getNumber():d}_en"),
                HlsNetNodeOutLazy(netlist, [], valCache, HVoidOrdering, name=f"bb{mb.getNumber():d}_orderingIn"),
                blockFsms.get(mb))
            blockMeta[mb] = mbMeta

    def _prunebackedgesOfFreeRunningLoops(self):
        """
        If the loop has no data dependency on backedges the loop iterations are independent may be overlapped.
        This is achieved by removing of backedges from this loop which would otherwise stall the loop until the previous iteration
        completes.
        """
        originalMir = self.originalMir
        mir = self.originalMir
        MRI = mir.mf.getRegInfo()
        for mb in originalMir.mf:
            mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
            if mbMeta.needsControl and mbMeta.isLoopHeader:
                # if the only enter is of reset type and
                # if every used backedge does not hold any data we may discard it
                # if this block has reset predecessor, some edge may have channelInitValues
                compatible = True
                edgesToDiscard: List[Tuple[MachineEdge, MachineEdgeMeta]] = []
                succFms = mbMeta.fsm
                for pred in mb.predecessors():
                    predFsm = self.blockMeta[pred].fsm
                    if predFsm is not None and predFsm is succFms:
                        # can not discard jump in the same FSM
                        continue

                    e = (pred, mb)
                    eMeta: MachineEdgeMeta = self.edgeMeta[e]
                    eT = eMeta.etype
                    if eT in (MACHINE_EDGE_TYPE.DISCARDED, MACHINE_EDGE_TYPE.RESET):
                        continue

                    elif eT == MACHINE_EDGE_TYPE.FORWARD:
                        # this loop is executed after some previous code, this loop needs to know that it needs to wait for it
                        compatible = False
                        break

                    elif eT == MACHINE_EDGE_TYPE.BACKWARD:
                        # backedge will be discarded if has no live ins
                        lives = mir.liveness[pred][mb]
                        if any(_regIsValidLiveIn(mir.regToIo, MRI, liveIn) for liveIn in lives):
                            compatible = False
                            break

                    assert eT in (MACHINE_EDGE_TYPE.NORMAL, MACHINE_EDGE_TYPE.BACKWARD), eT
                    edgesToDiscard.append((e, eMeta))

                if compatible and edgesToDiscard:
                    if succFms is None:
                        mbMeta.isLoopHeaderOfFreeRunning = True
                        mbMeta.needsControl = False
                    for _, eMeta in edgesToDiscard:
                        # assert eMeta.inlineRstDataFromEdge is None, ("Can not discard edge holding reset data", eMeta)
                        eMeta.etype = MACHINE_EDGE_TYPE.DISCARDED
                else:
                    pass
                    # [todo] try hoist loop prequel as an async call
                    # :ivar isLoopAsyncPrequel: if true, this block is loop async prequel.
                    # The prequel extraction is possible if it can be asynchronously executed. This is the case
                    # when loop does not have any non-reset entry and no exit.
                    # Prequel runs exactly once for each iteration and it does not need to wait for loop live ins.

    def _collectBlockNeighborsForLoop(self, loop: MachineLoop,
                                      blocksUsingChannelsForLiveouts: SetList[MachineBasicBlock],
                                      blocksUsingChannelsForLiveins: SetList[MachineBasicBlock]):
        header = loop.getHeader()
        self._collectBlockNeighbors(header, DIRECTION.IN, blocksUsingChannelsForLiveouts, blocksUsingChannelsForLiveins)
        for exitEdge in loop.getExitEdges():
            self._collectBlockNeighbors(exitEdge[0], DIRECTION.OUT, blocksUsingChannelsForLiveouts, blocksUsingChannelsForLiveins)

        for subLoop in loop:
            self._collectBlockNeighborsForLoop(subLoop, blocksUsingChannelsForLiveouts, blocksUsingChannelsForLiveins)

    def _initEdgeMeta(self, mf: MachineFunction):
        blocksUsingChannelsForLiveouts: SetList[MachineBasicBlock] = SetList()
        blocksUsingChannelsForLiveins: SetList[MachineBasicBlock] = SetList()

        for loop in self.loops:
            self._collectBlockNeighborsForLoop(loop, blocksUsingChannelsForLiveouts, blocksUsingChannelsForLiveins)

        edgeMeta: Dict[MachineEdge, MachineEdgeMeta] = self.edgeMeta
        MRI: MachineRegisterInfo = self.originalMir.mf.getRegInfo()
        for mb in mf:
            mb: MachineBasicBlock
            for suc in mb.successors():
                e = (mb, suc)
                if e in self.backedges:
                    eType = MACHINE_EDGE_TYPE.BACKWARD
                    tryToFindRegWhichCanBeUsedAsControl = True
                elif mb in blocksUsingChannelsForLiveouts:
                    eType = MACHINE_EDGE_TYPE.FORWARD
                    tryToFindRegWhichCanBeUsedAsControl = True
                else:
                    eType = MACHINE_EDGE_TYPE.NORMAL
                    tryToFindRegWhichCanBeUsedAsControl = False

                em = edgeMeta[e] = MachineEdgeMeta(mb, suc, eType)
                if tryToFindRegWhichCanBeUsedAsControl:
                    self._tryToFindRegWhichCanBeUsedAsControl(self.originalMir, MRI, em.srcBlock, em.dstBlock, em)

        return edgeMeta

    def _mergeFsmsBasedOnSharedResourcesOfBlock(self,
                                                bbResources: SetList[SchedulingResourceType],
                                                fsmForResource: dict[SchedulingResourceType, SetList[MachineBasicBlock]],
                                                fsmForBlock: dict[MachineBasicBlock, SetList[MachineBasicBlock]]):
        """
        merge all FSMs for resources used inside of this block inside of a single FSM
        """
        # find first existing fsm in advance so we can merge more efficly
        # without excesime update of sets
        newFsmBBs = None
        for resource in bbResources:
            fsm = fsmForResource.get(resource)
            if fsm is not None:
                newFsmBBs = fsm
                break

        if newFsmBBs is None:
            newFsmBBs = SetList()

        # for every resource, query existing fsms and merge them into one
        for resource in bbResources:
            fsm = fsmForResource.get(resource)
            if fsm is newFsmBBs:
                continue
            if fsm is not None:
                newFsmBBs.extend(fsm)
            fsmForResource[resource] = newFsmBBs

        # now all FSMs for all resources are merged into one (and replaced with it)

        # update fsm for all blocks
        for bb in tuple(newFsmBBs):
            curBbFsm = fsmForBlock.get(bb)
            if curBbFsm is not None and curBbFsm is not newFsmBBs:
                newFsmBBs.extend(curBbFsm)
                for bb2 in curBbFsm:
                    fsmForBlock[bb2] = newFsmBBs
                fsmForBlock[bb] = newFsmBBs

        return newFsmBBs

    def _mergeFsmsForSequenceOfBlocks(self, blocks: Sequence[MachineBasicBlock],
                                      sharedResourcesUsedByBlock: dict[MachineBasicBlock, SetList[SchedulingResourceType]],
                                      fsmForResource: dict[SchedulingResourceType, SetList[MachineBasicBlock]],
                                      fsmForBlock: dict[MachineBasicBlock, SetList[MachineBasicBlock]]):
        resourcesUsedByBlocks = SetList()
        newFsmBBs = None
        for bb in blocks:
            resources = sharedResourcesUsedByBlock.get(bb)
            if resources is not None:
                resourcesUsedByBlocks.extend(resources)

            if newFsmBBs is None:
                # find some existing fsm so we can use it as a base in order
                # to optimize merge of sets of fsm blocks
                fsm = fsmForBlock.get(bb)
                if fsm is not None:
                    newFsmBBs = fsm

        if newFsmBBs is None:
            newFsmBBs = SetList()

        # iterate all blocks inside of loop and merge them into a single FSM
        for bb in blocks:
            if bb in newFsmBBs:
                continue

            curFsm = fsmForBlock.get(bb)
            if curFsm is not None and curFsm is not newFsmBBs:
                newFsmBBs.extend(curFsm)
                for bb2 in curFsm:
                    fsmForBlock[bb2] = newFsmBBs
            else:
                newFsmBBs.append(bb)
                fsmForBlock[bb] = newFsmBBs

        for resource in resourcesUsedByBlocks:
            fsmForResource[resource] = newFsmBBs

    def _detectFsmsSharedResources(self, netlist:"HlsNetlistCtx", mf: MachineFunction):
        constraints: SchedulingResourceConstraints = netlist.scheduler.resourceUsage.resourceConstraints
        resourcesAvailable = copy(constraints)
        # discover which resources will have to be shared
        # thus requiring some form of FSM to manage access
        blocksUsingLimitedResource: dict[SchedulingResourceType, SetList[MachineBasicBlock]] = {}
        limitedResourcesUsedByBlock: dict[MachineBasicBlock, SetList[SchedulingResourceType]] = {}
        sharedResources: set[SchedulingResourceType] = set()

        MRI = mf.getRegInfo()
        for mb in mf:
            mb: MachineBasicBlock
            # mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
            bbResources = limitedResourcesUsedByBlock[mb] = SetList()
            for instr in mb:
                resource = self.originalMir._getSchedulingResourceForInstruction(MRI, instr)
                if resource is not None:
                    curAvailable: Optional[int] = resourcesAvailable.get(resource, None)
                    if curAvailable is not None:
                        bbResources.append(resource)
                        users = blocksUsingLimitedResource.get(resource)
                        if users is None:
                            users = blocksUsingLimitedResource[resource] = SetList()
                        users.append(mb)

                        if curAvailable == 0:
                            sharedResources.add(resource)
                        curAvailable -= 1
                        resourcesAvailable[resource] = curAvailable

        sharedResourcesUsedByBlock: dict[MachineBasicBlock, SetList[SchedulingResourceType]] = {
            mb: SetList(r for r in resources if resourcesAvailable[r] < 0)
            for mb, resources in  limitedResourcesUsedByBlock.items()}
        return sharedResourcesUsedByBlock

    def _detectFsms(self, netlist:"HlsNetlistCtx", mf: MachineFunction) -> dict[MachineBasicBlock, SetList[MachineBasicBlock]]:
        """
        if there are more instructions which contain access to some resource
        which does not support arbitration (e.g. scalar input or output port) (and the resource must be shared)
        all blocks containing this must be inside same ArchElementFsm
        In some cases when the resource is limiting factor all blocks in loop or on some
        path should be collected into fsm because they wont be able to execute
        because resource is locked for some other instruction in the region.
        """
        sharedResourcesUsedByBlock = self._detectFsmsSharedResources(netlist, mf)
        loops = self.loops
        fsmForResource: dict[SchedulingResourceType, SetList[MachineBasicBlock]] = {}
        fsmForBlock: dict[MachineBasicBlock, SetList[MachineBasicBlock]] = {}
        seenLoops: set[MachineLoop] = set()
        for mb in mf:
            mb: MachineBasicBlock
            bbSharedResources = sharedResourcesUsedByBlock[mb]
            if not bbSharedResources:
                continue
            newFsmBBs = self._mergeFsmsBasedOnSharedResourcesOfBlock(bbSharedResources, fsmForResource, fsmForBlock)
            newFsmBBs.append(mb)
            fsmForBlock[mb] = newFsmBBs

            loop = loops.getLoopFor(mb)
            # if mb uses shared resource put all blocks of fsm into loop because execution of another
            # iteration will be locked anyway because we can not speculate use of this resource
            # and thus we can not speculate execution of next iteration until the previous one finishies
            if loop:
                loop: MachineLoop
                if loop in seenLoops:
                    continue

                self._mergeFsmsForSequenceOfBlocks(list(loop.getBlocks()), sharedResourcesUsedByBlock, fsmForResource, fsmForBlock)
                seenLoops.add(loop)

            else:
                # if block is not in the loop whole function must be in same FSM because nothing can be speculated
                self._mergeFsmsForSequenceOfBlocks(mf, sharedResourcesUsedByBlock, fsmForResource, fsmForBlock)
                break  # now all blocks should be merged into a single FSM

        return fsmForBlock

    @override
    def runOnHlsNetlistImpl(self, netlist: "HlsNetlistCtx"):
        from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist

        originalMir: HlsNetlistAnalysisPassMirToNetlist = netlist.getAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        self.netlist = netlist
        self.platform = netlist.platform
        self.originalMir = originalMir
        self.blockMeta = originalMir.blockMeta
        self.loops: MachineLoopInfo = originalMir.loops
        self.backedges = originalMir.backedges
        self.edgeMeta = originalMir.edgeMeta

        blockFsms = self._detectFsms(netlist, originalMir.mf)
        self._initBlockMeta(originalMir.mf, netlist, originalMir.valCache, originalMir.blockMeta, blockFsms)
        self._initEdgeMeta(originalMir.mf)

        for mb in originalMir.mf:
            mb: MachineBasicBlock
            self._resolveBlockMeta(mb)

        entry: MachineBasicBlock = next(iter(originalMir.mf))
        entryMeta: MachineBasicBlockMeta = self.blockMeta[entry]
        # if everything from entry was inlined to reset values and the successor is infinite loop we do not need starter
        if entryMeta.needsStarter and not entryMeta.needsControl and entry.succ_size() == 1:
            suc = next(iter(entry.successors()))
            sucMeta: MachineBasicBlockMeta = self.blockMeta[suc]
            if (self.loops.isLoopHeader(suc) and
                self.blockMeta[suc].rstPredeccessor is entry and
                not sucMeta.needsControl):
                entryMeta.needsStarter = False

        self._prunebackedgesOfFreeRunningLoops()

        for mb in originalMir.mf:
            mbMeta: MachineBasicBlockMeta = self.blockMeta[mb]
            if mbMeta.needsControl and not mbMeta.needsStarter and mb.pred_size() == 0:
                mbMeta.needsStarter = True

