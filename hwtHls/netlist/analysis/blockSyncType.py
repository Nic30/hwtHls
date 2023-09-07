from typing import Set, List, Dict, Optional, Tuple

from hwt.hdl.types.defs import BIT
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineLoopInfo, \
    MachineLoop, MachineInstr, Register, TargetOpcode, MachineFunction, MachineRegisterInfo
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeOutLazy
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import \
    MachineEdgeMeta, MachineEdge, MACHINE_EDGE_TYPE, MachineLoopId
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


class HlsNetlistAnalysisPassBlockSyncType(HlsNetlistAnalysisPass):
    '''
    This pass updates blockSync dictionary in :class:`hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist` with
    flags which are describing what type of synchronization for block should be used.

    :note: This is thread level synchronization of control flow in blocks not RTL type of synchronization.
        That means this does not solve synchronization of pipeline stages but the synchronization between accesses to exclusive resources.

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

    :note: This is called uppon once the datapath in blocks is resolved.
        This is because we need to know HlsNetlistAnalysisPassDataThreadsForBlocks
        and it can be only obtained once datapath in blocks was constructed.
        :see: :class:`~.HlsNetlistAnalysisPassDataThreadsForBlocks`
    '''

    def _resolveRstPredecessor(self, mb: MachineBasicBlock,
                               mbSync: MachineBasicBlockMeta,
                               loop: MachineLoop) -> Optional[MachineBasicBlock]:
        if loop.getHeader() != mb:
            # can not extract reset if this not a top loop
            return mbSync.rstPredeccessor

        topLoop = loop
        while True:
            p = topLoop.getParentLoop()
            if p is None or p.getHeader() != mb:
                break

        if mbSync.rstPredeccessor is None and mb.pred_size() >= 2:
            # check if some predecessor is bb0 and check if all other predecessors are reenter from the loop which has this block as header
            p0 = None
            mostOuterOuterPred = None
            for pred in mb.predecessors():
                # one of predecessors may possibly be suitable for reset extraction
                if pred.pred_size() == 0:
                    if p0 is not None:
                        # there are multiple enters from bb0 we can not extract and this should be already optimized away
                        return mbSync.rstPredeccessor
                    p0 = pred
                elif not topLoop.containsBlock(pred):
                    # can not extract because this in not top loop
                    return mbSync.rstPredeccessor
                else:
                    mostOuterOuterPred = pred
            assert mostOuterOuterPred is not None

            mbSync.rstPredeccessor = p0
            rstE: MachineEdgeMeta = self.edgeMeta[(p0, mb)]
            rstE.etype = MACHINE_EDGE_TYPE.RESET
            rstE.inlineRstDataToEdge = (mostOuterOuterPred, mb)

        return mbSync.rstPredeccessor

    def _tryToFindRegWhichCanBeUsedAsControl(self, mir: "HlsNetlistAnalysisPassMirToNetlist", MRI: MachineRegisterInfo,
                                             pred: MachineBasicBlock, mb: MachineBasicBlock,
                                             eMeta: MachineEdgeMeta) -> Optional[Register]:
        assert eMeta.srcBlock is pred and eMeta.dstBlock is mb, (eMeta, pred, mb)
        if eMeta.reuseDataAsControl is not None:
            return eMeta.reuseDataAsControl
        for liveIn in mir.liveness[pred][mb]:
            # [todo] prefer using same liveIns from every predecessor
            # [todo] prefer using variables which are used the earlyest
            if mir._regIsValidLiveIn(MRI, liveIn):
                latestDefInPrevBlock = None
                for predMI in pred:
                    if predMI.definesRegister(liveIn):
                        latestDefInPrevBlock = predMI
                if latestDefInPrevBlock is not None and\
                    latestDefInPrevBlock.getOpcode() == TargetOpcode.HWTFPGA_MUX and\
                    latestDefInPrevBlock.getNumOperands() == 2 and\
                    latestDefInPrevBlock.getOperand(1).isCImm():
                    # skip because this will be trivially sinked
                    continue

                eMeta.reuseDataAsControl = liveIn
                return liveIn

        return None

    def _resolveUsedLoops(self, mb: MachineBasicBlock, mbSync: MachineBasicBlockMeta, loop: MachineLoop):
        mir = self.originalMir
        MRI = mir.mf.getRegInfo()
        assert loop.getHeader() == mb, (mb, loop)
        edgeMeta: MachineEdgeMeta = self.edgeMeta
        topLoop = loop
        mbSync.isLoopHeader = True
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

    def _makeNormalEdgeForward(self, MRI: MachineRegisterInfo, em: MachineEdgeMeta):
        if em.etype == MACHINE_EDGE_TYPE.NORMAL:
            em.etype = MACHINE_EDGE_TYPE.FORWARD
            self._tryToFindRegWhichCanBeUsedAsControl(self.originalMir, MRI, em.srcBlock, em.dstBlock, em)

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
    #            if mir._regIsValidLiveIn(MRI, liveIn):
    #                someLiveInFound = True
    #                break
    #        if not someLiveInFound:
    #            return False
    #
    #    return True

    def _resolveBlockMeta(self, mb: MachineBasicBlock):
        """
        The code needs a synchronization if it starts a new thread without data dependencies and has predecessor thread.

        :note: They synchronization is always marked for the start of the thread.
        """
        # resolve control enable flag for a block
        mbSync: MachineBasicBlockMeta = self.blockSync[mb]
        mbThreads: List[Set[HlsNetNode]] = self.threadsPerBlock[mb]
        loops: MachineLoopInfo = self.loops
        needsControlOld = mbSync.needsControl

        if mb.pred_size() == 0 and mb.succ_size() == 0:
            mbSync.needsControl = True
            mbSync.needsStarter = True
        else:
            predThreadIds: Set[int] = set()
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                predThreadIds.update(id(t) for t in self.threadsPerBlock[pred])
            threadsStartingThere = [t for t in mbThreads if id(t) not in predThreadIds]

            # if mb.pred_size() == 0:
            #    if mb.succ_size() == 1:
            #        suc = tuple(mb.successors())[0]
            #        if self._resolveRstPredecessor(suc, self.blockSync[suc]) is not mb:
            #            mbSync.needsStarter = True
            #    else:
            #        mbSync.needsStarter = True

            if self.loops.isLoopHeader(mb):
                loop: MachineLoop = loops.getLoopFor(mb)
                # The synchronization is not required if it could be only by the data itself.
                # It can be done by data itself if there is an single output/write which has all
                # input as transitive dependencies (unconditionally.) And if this is an infinite cycle.
                # So we do not need to check the number of executions.
                self._resolveRstPredecessor(mb, mbSync, loop)
                self._resolveUsedLoops(mb, mbSync, loop)

                if not mbSync.needsControl:
                    # if not loop.hasNoExitBlocks():
                    #    # need sync to synchronize code behind the loop
                    #    mbSync.needsControl = True

                    if mbThreads and HlsNetlistAnalysisPassDataThreadsForBlocks.threadContainsNonConcurrentIo(mbThreads[0]):
                        mbSync.needsControl = True

                    elif (len(mbThreads) != 1 or
                          (mb.pred_size() > 1 and
                           (mb.pred_size() != 2 or not mbSync.rstPredeccessor)  # and
                            # not self._hasSomeLiveInFromEveryPredec(mb)
                           )
                          ):
                        # multiple independent threads in body or more entry points to a loop
                        loopBodySelfSynchronized = True
                        for pred in mb.predecessors():
                            pred: MachineBasicBlock
                            isLoopReenter = loop.containsBlock(pred)
                            # reenter does not need explicit sync because it is synced by data
                            # rstPredeccessor does not need explicit sync because it will be inlined to reset values
                            if not isLoopReenter and mbSync.rstPredeccessor is not pred:
                                loopBodySelfSynchronized = False
                                break

                        if loopBodySelfSynchronized and mb.pred_size() == 2:
                            pass
                        else:
                            mbSync.needsControl = True

                    elif mb.succ_size() > 1:
                        mbSync.needsControl = True
                        # # we can use input data as control to activate this block
                        # # so we do not require control if there is some data
                        # mbSync.needsControl = not self._hasSomeLiveInFromEveryPredec(mb)

                    else:
                        sucThreadIds = set()
                        for suc in mb.successors():
                            for t in self.threadsPerBlock[suc]:
                                sucThreadIds.add(id(t))
                        if len(sucThreadIds) > 1:
                            mbSync.needsControl = True

                # if mbSync.needsControl and not mbSync.uselessOrderingFrom:
                #    loopHasOnly1Thread = True
                #    onlyDataThread = None
                #    for _mb in loop.getBlocks():
                #        _mbThreads = self.threadsPerBlock[_mb]
                #        if len(_mbThreads) > 1:
                #            loopHasOnly1Thread = True
                #        elif onlyDataThread is None:
                #            if _mbThreads:
                #                onlyDataThread = _mbThreads[0]
                #        elif _mbThreads:
                #            if onlyDataThread is not _mbThreads[0]:
                #                loopHasOnly1Thread = False
                #    # [fixme] if the block is part of FSM there is a problem caused by storing of control bit to register
                #    #         the FSM detect state transitions by the time when write happens
                #    #         if we allow the write of this bit before all IO is finished the FSM transition detection alg.
                #    #         will resolve IO as to skip if after control bit is written which is incorrect
                #    if loopHasOnly1Thread:
                #        for pred in mb.predecessors():
                #            if loop.containsBlock(pred):
                #                mbSync.uselessOrderingFrom.add(pred)

            elif not mbSync.needsControl:
                needsControl = False
                if (len(threadsStartingThere) > 1 or
                    any(HlsNetlistAnalysisPassDataThreadsForBlocks.threadContainsNonConcurrentIo(t) for t in threadsStartingThere)):
                    needsControl = True
                elif (bool(mbThreads) and
                        (
                            any(self.blockSync[pred].needsControl for pred in mb.predecessors()) or
                            any(self.blockSync[suc].needsControl for suc in mb.successors())
                        )
                    ):
                    needsControl = True
                elif (mbSync.needsStarter and
                          (mb.succ_size() == 0 or
                           any(loops.getLoopFor(suc) is None for suc in mb.successors()))):
                    needsControl = True
                elif self._isPredecessorOfBlocksWithPotentiallyConcurrentIoAccess(mb):
                    needsControl = True

                mbSync.needsControl = needsControl

        if not needsControlOld and mbSync.needsControl:
            self._onBlockNeedsControl(mb)

    def _getPotentiallyConcurrentIoAccessFromSuccessors(self, mb: MachineBasicBlock):
        backedges = self.backedges
        accesses: Dict[Register, Set[MachineInstr]] = {}
        for suc in mb.successors():
            suc: MachineBasicBlock
            if (mb, suc) in backedges:
                # skip because on this edge there will be some sort of synchronization naturally
                # we do not have to mark it explicitly
                continue

            sucAccesses = self._getPotentiallyConcurrentIoAccess(suc)
            for reg, accessSet in sucAccesses.items():
                accs = accesses.get(reg, None)
                if accs is None:
                    accesses[reg] = accs = set()
                accs.update(accessSet)

        return accesses

    def _getPotentiallyConcurrentIoAccess(self, mb: MachineBasicBlock):
        """
        :note: Potentially concurrent accesses are those which are to same interface and are in different code branches which may execute concurrently.
        """
        accesses = self._getPotentiallyConcurrentIoAccessFromSuccessors(mb)
        for instr in mb:
            instr: MachineInstr
            opc = instr.getOpcode()
            if opc not in (TargetOpcode.HWTFPGA_CLOAD, TargetOpcode.HWTFPGA_CSTORE):
                continue

            io = instr.getOperand(1).getReg()
            # overwrite because now there is a single load/store and all successors load/stores are ordered after it
            accSet = accesses.get(io, None)
            if accSet is None:
                accesses[io] = {instr, }
            else:
                accSet.add(instr)

        return accesses

    def _isPredecessorOfBlocksWithPotentiallyConcurrentIoAccess(self, mb: MachineBasicBlock):
        accesses = self._getPotentiallyConcurrentIoAccessFromSuccessors(mb)
        return any(len(accessList) > 1 for accessList in accesses.values())

    def _onBlockNeedsControl(self, mb: MachineBasicBlock):
        blockSync = self.blockSync
        mbSync: MachineBasicBlockMeta = blockSync[mb]
        rstPred = mbSync.rstPredeccessor
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

            predMbSync: MachineBasicBlockMeta = blockSync[pred]
            canUseDataAsControl = False
            eMeta: MachineEdgeMeta = self.edgeMeta[(pred, mb)]
            if loop is not None or (pred, mb) in self.backedges or eMeta.etype == MACHINE_EDGE_TYPE.FORWARD:
                canUseDataAsControl = self._tryToFindRegWhichCanBeUsedAsControl(mir, MRI, pred, mb, eMeta) is not None

            if not canUseDataAsControl and not predMbSync.needsControl:
                predMbSync.needsControl = True
                if not predMbSync.needsStarter and not pred.pred_size():
                    predMbSync.needsStarter = True

                self._onBlockNeedsControl(pred)

        for suc in mb.successors():
            mbSync: MachineBasicBlockMeta = blockSync[suc]
            if not mbSync.needsControl:
                mbSync.needsControl = True
                self._onBlockNeedsControl(suc)

    def _initEdgeMeta(self, mf: MachineFunction):
        edgeMeta: Dict[MachineEdge, MachineEdgeMeta] = self.edgeMeta
        for mb in mf:
            mb: MachineBasicBlock
            for suc in mb.successors():
                e = (mb, suc)
                eType = MACHINE_EDGE_TYPE.BACKWARD if e in self.backedges else MACHINE_EDGE_TYPE.NORMAL
                edgeMeta[e] = MachineEdgeMeta(mb, suc, eType)

        return edgeMeta

    # def _resolveEdgeMeta(self, mf: MachineFunction):
    #    edgeMeta = self.edgeMeta
    #    loops = self.loops
    #    for mb in mf:
    #        mb: MachineBasicBlock
    #        loop: MachineLoop = loops.getLoopFor(mb)
    #        if loop is not None:
    #            if loop.getHeader() != mb:
    #                continue
    #
    #                loop = loop
    #            loop = None
    #        loop.get
    #
    @staticmethod
    def constructBlockMeta(mf: MachineFunction,
                           netlist: HlsNetlistCtx,
                           valCache: MirToHwtHlsNetlistValueCache,
                           blockSync:Dict[MachineBasicBlock, MachineBasicBlockMeta]):
        for mb in mf:
            mb: MachineBasicBlock
            mbSync = MachineBasicBlockMeta(
                mb,
                HlsNetNodeOutLazy(netlist, [], valCache, BIT, name=f"bb{mb.getNumber():d}_en"),
                HlsNetNodeOutLazy(netlist, [], valCache, HVoidOrdering, name=f"bb{mb.getNumber():d}_orderingIn"))
            blockSync[mb] = mbSync

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
            mbSync: MachineBasicBlockMeta = self.blockSync[mb]
            if mbSync.needsControl and mbSync.isLoopHeader:
                # if the only enter is of reset type and
                # if every used backedge does not hold any data we may discard it
                # if this block has reset predecessor, some edge may have channelInitValues
                compatible = True
                edgesToDiscard: List[Tuple[MachineEdge, MachineEdgeMeta]] = []
                for pred in mb.predecessors():
                    e = (pred, mb)
                    eMeta: MachineEdgeMeta = self.edgeMeta[e]
                    eT = eMeta.etype
                    if eT in (MACHINE_EDGE_TYPE.DISCARDED, MACHINE_EDGE_TYPE.FORWARD, MACHINE_EDGE_TYPE.RESET):
                        continue
                    elif eT == MACHINE_EDGE_TYPE.BACKWARD:
                        # backedge will be discarded if has no live ins
                        lives = mir.liveness[pred][mb]
                        if any(mir._regIsValidLiveIn(MRI, liveIn) for liveIn in lives):
                            compatible = False
                            break
                    edgesToDiscard.append((e, eMeta))

                if compatible and edgesToDiscard:
                    mbSync.isLoopHeaderOfFreeRunning = True
                    for _, eMeta in edgesToDiscard:
                        eMeta.etype = MACHINE_EDGE_TYPE.DISCARDED

    def run(self):
        from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist

        originalMir: HlsNetlistAnalysisPassMirToNetlist = self.netlist.getAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        threads: HlsNetlistAnalysisPassDataThreadsForBlocks = self.netlist.getAnalysis(HlsNetlistAnalysisPassDataThreadsForBlocks)

        self.originalMir = originalMir
        self.threadsPerBlock = threads.threadsPerBlock
        self.blockSync = originalMir.blockSync
        self.loops: MachineLoopInfo = originalMir.loops
        self.backedges = originalMir.backedges
        self.edgeMeta = originalMir.edgeMeta
        self._initEdgeMeta(originalMir.mf)

        for mb in originalMir.mf:
            mb: MachineBasicBlock
            self._resolveBlockMeta(mb)

        entry: MachineBasicBlock = next(iter(originalMir.mf))
        entrySync: MachineBasicBlockMeta = self.blockSync[entry]
        # if everything from entry was inlined to reset values and the successor is infinite loop we do not need starter
        if entrySync.needsStarter and not entrySync.needsControl and entry.succ_size() == 1:
            suc = next(iter(entry.successors()))
            sucSync: MachineBasicBlockMeta = self.blockSync[suc]
            if (self.loops.isLoopHeader(suc) and
                self.blockSync[suc].rstPredeccessor is entry and
                not sucSync.needsControl):
                entrySync.needsStarter = False

        self._prunebackedgesOfFreeRunningLoops()

        for mb in originalMir.mf:
            mbSync: MachineBasicBlockMeta = self.blockSync[mb]
            if mbSync.needsControl and not mbSync.needsStarter and mb.pred_size() == 0:
                mbSync.needsStarter = True

