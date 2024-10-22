from typing import Set, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, \
    MachineLoop
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, \
    HlsNetNodeOutAny, unlink_hls_node_input_if_exists
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOutLazy_replace, \
    HlsNetNodeOut_connectHlsIn_crossingHierarchy
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.ssa.translation.llvmMirToNetlist.blockEn import resolveBlockEn
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import HlsNetlistAnalysisPassMirToNetlistDatapath, \
    BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta, ADD_ORDERING_PREPEND
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MACHINE_EDGE_TYPE
from hwtHls.ssa.translation.llvmMirToNetlist.resetValueExtract import ResetValueExtractor
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache


class HlsNetlistAnalysisPassMirToNetlist(HlsNetlistAnalysisPassMirToNetlistDatapath):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist (this class specifically contains control related things)

    MIR to HlsNetlist translation
    =============================
    
    * Achieving overhead-free conversion from assembly (MIR) to dataflow (HlsNetlist) is challenging.
      There are numerous corner cases and complex timing and data dependency analysis is often required.
      It is also hard to visualize, check and debug. 
    * The MIR is assembler like format, it uses jump instructions, has stack and data is globally visible.
      The execution happens on per instruction basis.
    * The HlsNetlist is dataflow format without stack. In HlsNetlist the control flow is represented as a enable flag,
      any instruction can run in parallel if restrictions allow it. `MIR CFG translation`_
    * The blocks in MIR may have livein and liveout registers. Use and def of them is controlled by CFG.
      Some of them can be just wire while others need explicit channels and complex synchronization.
      `MIR block livein/liveout translation`_
    * The use of internal channels and IO brings the issue of synchronization synthesis. This
      Various types of synchronization protocols can be used. Complicated situation where parts of circuit 
      can implement flushing or can run asynchronously. 
      `HlsNetlist channel synchronization inference`_
    

    MIR CFG translation
    ===================
    
    * If we use if-conversion_ to reduce code to a single block it would be very hard to extract
      asynchronously running loops and other features running pseudo independently in the MIR.
    * From this reason we use if-conversion_ approach only for jumps which are not loop entry,re-entry or exit. (C++ :class:`VRegIfConverter`)
    * The block enable condition can be computed from all jumps to block.
    * The block jump condition is curBlock.enable & branch.condition
    * :class:`HlsNetlistAnalysisPassBlockSyncType` is used to decide how to implement control for each block and jump.
    * If the liveouts from block use channels:
      * Some channel can be reused to pass branch flag to successor.
      * Channels of registers must not cause parent stall if the branch was not used.
      * Implemented in :meth:`hwtHls.netlist.nodes.loopChannelGroup.LoopChanelGroup.getChannelUsedAsControl`
    * The branches of locked sections and loops need to manage locks which may select
      subset of incoming channels.
      * :see: :class:`hwtHls.netlist.nodes.loopControl.HlsNetNodeLoopStatus`
    * Some data storages like registers for locks may also need to be modified out of CFG.
      * :see: :class:`hwtHls.architecture.transformation.loopControlLowering.HlsAndRtlNetlistPassLoopControlLowering`
    

    MIR block livein/liveout translation
    ====================================
    
    * The register may be just wire, register or it may pass trough channel depending on CFG jump type.
    * If liveins are passed trough channels the arbitration is required. :see: :meth:`~._handleArbitrationLogicOnLoopInput` 
    * The use of just wire is cheap while use of channel is costly.
      Channels are used for asynchronous sections like loops and backedges.
      The register value arrival time may be different for each register and branch.
      From this reason, each register or wire corresponds to just single register.
      The scheduler later resolves timing. Channels for some registers may be
      merged in :class:`RtlArchPassChannelMerge`


    HlsNetlist synchronization inference
    ====================================
    
    * The IO port represent internal or external IO access. The IO may be only virtual and do not have
      to physically exist. Such virtual reads/writes are used to implement stalling etc. 
    * If any specific synchronization protocol (e.g. 2-state ready-valid handshake) is used at this point,
      it would make further analysis and optimizations drastically more complex.
      From this reason the synchronization logic is later constructed from node schedule,
      parent node preferences and flags for each node in :class:`RtlArchPassSyncLowering`.
    * Resolving of stage and IO port enable condition is hard to debug, because the HlsNetlist does not have any linear code flow.
    * User input may contain synchronization errors. For example, the user code can contain obvious deadlock.
      If any optimization is applied during translation it is nearly impossible for user to debug.
      Because this infers the synchronization from CFG for the circuit and it dissolves blocks.
      From this reason a translation from MIR to HlsNetlist must be done 1 to 1 as much as possible.
    * In this stage we just just add extraCond, skipWhen condition to channel ports.


    MIR to HlsNetlist translation implementation details
    ====================================================
    
    * Forward analysis of block synchronization type to avoid complexities on synchronization type change.
    * Each ordering between IO is strictly specified (can be specified to none). This is used to generate channel synchronization
      flags and to improve thread level parallelism.
    * MIR object may override its translation. This is used to implemented various plugins with minimum effort.
      For example the read from some interface may lower itself to multiple nodes which will implement bus protocol.
    * Loops and backedges are handled explicitly. The loop recognizes "break", "continue", "predecessor" branches and has internal state
      which describes if the loop is busy or not. This state is used to control individual channels.
 
 
    Dictionary
    ==========
    
    .. _if-conversion:
      * inline block code to parent
      * use predication_ and MUXes to select between state where block was and was not executed
    
    .. _predication:
      * add enable flag to instruction
    
    """

    def extractRstValues(self, mf: MachineFunction):
        with self.dbgTracer.scoped(ResetValueExtractor, None):
            return ResetValueExtractor(self.valCache, self.liveness,
                self.blockMeta, self.edgeMeta, self.regToIo,
                self.dbgTracer
            ).apply(mf)

    def _getControlFromPred(self, pred: MachineBasicBlock, mb: MachineBasicBlock,
                            mbSync: MachineBasicBlockMeta, eMeta: MachineEdgeMeta):
        edge = (pred, mb)
        # insert explicit sync on control input
        dataAsControl = eMeta.reuseDataAsControl

        if dataAsControl is None:
            if mbSync.needsControl:
                control = eMeta.getBufferForReg(edge).obj
            else:
                control = None
        else:
            assert mbSync.needsControl
            control = eMeta.getBufferForReg(dataAsControl)
            control = control.obj

        return control

    # def _collectLiveInDataChannels(self, pred: MachineBasicBlock,
    #                               mb: MachineBasicBlock,
    #                               blockLiveInMuxInputSync: BlockLiveInMuxSyncDict,
    #                               dataAsControl: Optional[Register],
    #                               MRI: MachineRegisterInfo):
    #    allInputDataChannels: List[HlsNetNodeExplicitSync] = []
    #    # for non backedge edges the sync is not required as the data is received from previous stage in pipeline or state in FSM
    #    for liveIn in self.liveness[pred][mb]:
    #        liveIn: Register
    #        if not self._regIsValidLiveIn(MRI, liveIn) or (dataAsControl is not None and liveIn == dataAsControl):
    #            continue
    #
    #        liveInSync: HlsNetNodeExplicitSync = blockLiveInMuxInputSync[(pred, mb, liveIn)]
    #        allInputDataChannels.append(liveInSync)
    #    return allInputDataChannels

    def _handleArbitrationLogicOnLoopInput(self, loopStatus: HlsNetNodeLoopStatus,
                                           pred: MachineBasicBlock,
                                           mb: MachineBasicBlock,
                                           eMeta: MachineEdgeMeta,
                                           control: HlsNetNodeReadOrWriteToAnyChannel,
                                           # loopBusy: HlsNetNodeOut, loopBusy_n: HlsNetNodeOut,
                                           # allInputDataChannels: List[HlsNetNodeExplicitSync],
                                           # loopExecs: LoopPortGroup,
                                           # loopReenters: LoopPortGroup
                                           ):
        """
        .. figure:: _static/mirToNetlist_loopChannelPortConstruction.png
        """
        isReenter = any(l.headerBlockNum == mb.getNumber() for l in eMeta.reenteringLoops)
        if not isReenter:
            assert any(l.headerBlockNum == mb.getNumber() for l in eMeta.enteringLoops), mb

        if (eMeta.reenteringLoops if isReenter else eMeta.enteringLoops)[0].headerBlockNum == mb.getNumber():
            # if it is jumping to loop header
            lcg = eMeta.getLoopChannelGroup()
            if not lcg.members:
                lcg.appendWrite(control.associatedWrite, True)
            else:
                assert lcg.members and lcg.getChannelUsedAsControl() is control.associatedWrite, (eMeta, lcg.members)
            if isReenter:
                # cp, cpO =
                loopStatus.addReenterPort(pred.getNumber(), mb.getNumber(), lcg)
            else:
                # cp, cpO =
                loopStatus.addEnterPort(pred.getNumber(), mb.getNumber(), lcg)
        else:
            raise NotImplementedError("ask owner of channel for allocation")

        # assert isinstance(cp, HlsNetNodeRead), cp

        # loopPortRecord = (cpO, cp, allInputDataChannels)
        # if isReenter:
        #    loopReenters.append(loopPortRecord)
        # else:
        #    loopExecs.append(loopPortRecord)
        #
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
        controlRead: HlsNetNodeRead = lcg.getChannelUsedAsControl().associatedRead
        branchEnableAtDst = controlRead.getHlsNetlistBuilder().buildAnd(controlRead.getExtraCondDriver(), controlRead.getValidNB())
        valCache.add(mb, pred, branchEnableAtDst, False)

    def _resolveLoopIoSync(self, mb: MachineBasicBlock,
                           mbSync: MachineBasicBlockMeta,
                           loop: MachineLoop,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        assert mbSync.loopStatusNode is None, (mbSync, mbSync.loopStatusNode)
        mbSync.loopStatusNode = loopStatus = HlsNetNodeLoopStatus(self.netlist, f"loop_bb{mb.getNumber():d}")
        parentElm = mbSync.parentElement
        parentElm.addNode(loopStatus)
        assert mbSync.needsControl and mbSync.isLoopHeader, (
            "This should be called only for loop headers with physical loop, bb", mb.getNumber())
        # builder = parentElm.builder
        # loopReenters: LoopPortGroup = []
        # loopExecs: LoopPortGroup = []
        # loopBusy = loopStatus.getBusyOutPort()
        # loopBusy_n = builder.buildNot(loopBusy)
        # MRI = self.mf.getRegInfo()

        for pred in mb.predecessors():
            pred: MachineBasicBlock
            edge = (pred, mb)
            eMeta: MachineEdgeMeta = self.edgeMeta[edge]

            if eMeta.etype.isChannel():
                pass
            else:
                assert not eMeta.etype.isPhysicallyExisting(), eMeta
                continue

            control = self._getControlFromPred(pred, mb, mbSync, eMeta)
            # allInputDataChannels = self._collectLiveInDataChannels(
            #    pred, mb, blockLiveInMuxInputSync, dataAsControl, MRI)
            self._handleArbitrationLogicOnLoopInput(
                loopStatus, pred, mb, eMeta, control)  # , loopBusy, loopBusy_n,
                # allInputDataChannels, loopExecs, loopReenters

        # # loopBusy select if loop should process inputs from loopReenters or from loopExecs
        # # if busy skip channels for entry of the loop
        # # if not busy skip channels for reenter of the loop
        # _createSyncForAnyInputSelector(builder, loopReenters, loopBusy, loopBusy_n)
        # _createSyncForAnyInputSelector(builder, loopExecs, loopBusy_n, loopBusy)

        # for each exit skip wait on data if the loop was not executed
        if not loop.hasNoExitBlocks():
            # loop has exits
            self._resolveLoopIoSyncForExit(loopStatus, loop, mb)

    def _resolveBlockIoSyncForNonLoopHeader(self,
                                            mb: MachineBasicBlock,
                                            mbSync: MachineBasicBlockMeta,
                                            blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        inputCases: LoopChanelGroup = []
        for pred in mb.predecessors():
            pred: MachineBasicBlock
            edge = (pred, mb)
            eMeta: MachineEdgeMeta = self.edgeMeta[edge]

            if not eMeta.etype.isChannel():
                assert not eMeta.etype.isPhysicallyExisting(), eMeta
                continue

            control = self._getControlFromPred(pred, mb, mbSync, eMeta)
            assert control is not None, (pred, mb, eMeta)
            lcg = eMeta.getLoopChannelGroup()
            # [fixme] this can cause reordering
            LoopChanelGroup.appendToListOfPriorityEncodedReads(inputCases, None, None, lcg, f"{pred.getNumber():d}_to_{mb.getNumber():d}")

    def _constructChannelForLoopExitNotifyToHeader(self,
                                                   eMbSync: MachineBasicBlockMeta,
                                                   loopStatus: HlsNetNodeLoopStatus,
                                                   mb: MachineBasicBlock,
                                                   exitBlock: MachineBasicBlock,
                                                   exitSucBlock: MachineBasicBlock,
                                                   controlOrig: HlsNetNodeOutAny,
                                                   ):
        exitForHeaderR = self._constructBuffer(
            "loopExitNotify",
            exitBlock, mb,
            None,
            HVoidOrdering.from_py(None),
            isBackedge=True,
            isControl=True)
        # [todo] add exits also for parent loops
        # edgeMeta.buffersForLoopExit.append(exitForHeaderR) # :note: buffersForLoopExit is not for EXIT_NOTIFY_TO_HEADER
        exitForHeaderR.obj.setNonBlocking()
        exitForHeaderW: HlsNetNodeWriteBackedge = exitForHeaderR.obj.associatedWrite
        # this channel will asynchronously notify loop header, it is not required
        # to have ready sync signal
        exitForHeaderW._isBlocking = False
        exitForHeaderW.allocationType = CHANNEL_ALLOCATION_TYPE.IMMEDIATE
        exitForHeaderW._rtlUseReady = exitForHeaderR.obj._rtlUseReady = False
        # exitForHeaderW._rtlUseValid = exitForHeaderR.obj._rtlUseValid = False

        self._addExtraCond(exitForHeaderW, controlOrig, eMbSync.blockEn)
        # skipWhen is required because we do not want this to stall parent stage
        self._addSkipWhen_n(exitForHeaderW, controlOrig, eMbSync.blockEn)
        # r.channelInitValues = ((0,),)
        lcg = LoopChanelGroup([(exitBlock.getNumber(),
                                exitSucBlock.getNumber(),
                                LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER)])
        lcg.appendWrite(exitForHeaderW, True)
        loopStatus.addExitToHeaderNotifyPort(exitBlock.getNumber(), exitSucBlock.getNumber(), lcg)

    def _isExistingParentLoop(self, loop: MachineLoop, exitSucBlock: MachineBasicBlock):
        isExitFromParentLoop = False
        p: MachineLoop = loop.getParentLoop()
        while p is not None:
            if p.getHeader() == exitSucBlock or not p.containsBlock(exitSucBlock):
                if self.blockMeta[p.getHeader()].isLoopHeaderOfFreeRunning:
                    # parent loop was just found out to be without HW representation
                    break
                isExitFromParentLoop = True
                break
            p = p.getParentLoop()
        return isExitFromParentLoop

    def _resolveLoopIoSyncForExit(self, loopStatus: HlsNetNodeLoopStatus, loop: MachineLoop,
                                  mb: MachineBasicBlock):
        valCache: MirToHwtHlsNetlistValueCache = self.valCache

        loopIsHwLoop = not self.blockMeta[loop.getHeader()].isLoopHeaderOfFreeRunning
        # for every exit build a channel which notifies the loop status
        for edge in loop.getExitEdges():
            (exitBlock, exitSucBlock) = edge
            edgeMeta: MachineEdgeMeta = self.edgeMeta[edge]
            eMbSync: MachineBasicBlockMeta = self.blockMeta[exitBlock]

            edgeIsNotBackedge = edgeMeta.etype in (MACHINE_EDGE_TYPE.DISCARDED,
                                                   MACHINE_EDGE_TYPE.NORMAL)
            loopExitExits = edgeIsNotBackedge or\
                    not loopIsHwLoop or\
                    self._isExistingParentLoop(loop, exitSucBlock)

            # if exiting loop return token to HlsNetNodeLoopStatus
            if loopExitExits:
                # if it is exit from parent loop  we let parent loop add flags to write node
                eRead = None
                eWrite = None
            else:
                edgeDescriptor = edgeMeta.reuseDataAsControl if edgeMeta.reuseDataAsControl is not None else edge
                eRead = edgeMeta.getBufferForReg(edgeDescriptor)
                eRead: HlsNetNodeReadAnyChannel = eRead.obj
                # make read from exit channel the first read in successor block
                self.blockMeta[exitSucBlock].addOrderedNode(eRead, ADD_ORDERING_PREPEND)
                eWrite = eRead.associatedWrite
                assert isinstance(eWrite, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)), eWrite

            # register and optionally construct EXIT_NOTIFY_TO_HEADER port
            controlOrig = valCache.get(exitBlock, BranchOutLabel(exitSucBlock), BIT)
            if loopIsHwLoop:
                self._constructChannelForLoopExitNotifyToHeader(
                    eMbSync, loopStatus, mb, exitBlock, exitSucBlock, controlOrig)

            if eWrite is not None:
                # make write to exit channel the last last in block from which there is jump outside of loop
                # :note: ordering should be already added
                # eMbSync.addOrderedNode(eWrite, True)
                self._addExtraCond(eWrite, controlOrig, eMbSync.blockEn)
                self._addSkipWhen_n(eWrite, controlOrig, eMbSync.blockEn)
                eWrite._mayBecomeFlushable = False  # because it is useless, nothing after this should cause stall in loop body

                # register exit write for the loop
                lcg = eWrite._loopChannelGroup
                if lcg is None:
                    lcg = LoopChanelGroup([(exitBlock.getNumber(),
                                            exitSucBlock.getNumber(),
                                            LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)])
                    lcg.appendWrite(eWrite, True)

                lcg.associateWithLoop(loopStatus, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)

    def resolveControlForBlockWithChannelLivein(self,
                           mf: MachineFunction,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        """
        Construct the loop control logic at the header of the loop.
        :attention: expects :meth:`constructLiveInMuxes` to be called which should prepare all channels
        """
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockMeta = self.blockMeta[mb]

            if mbSync.isLoopHeaderOfFreeRunning:
                continue
            elif mbSync.needsControl:
                if mbSync.isLoopHeader:
                    loop = self.loops.getLoopFor(mb)
                    assert loop is not None
                    self._resolveLoopIoSync(mb, mbSync, loop, blockLiveInMuxInputSync)
                elif any(self.edgeMeta[(pred, mb)].etype.isChannel() for pred in mb.predecessors()):
                    self._resolveBlockIoSyncForNonLoopHeader(mb, mbSync, blockLiveInMuxInputSync)

    def resolveBlockEn(self, mf: MachineFunction):
        """
        Resolve control flow enable for instructions in the block.
        """
        return resolveBlockEn(self, mf, self.blockMeta)

    def connectOrderingPorts(self, mf: MachineFunction):
        """
        Finalize ordering connections after all IO is instantiated.
        """
        # cancel ordering between last IO at the end of the loop and write to control channel of that block
        # this allow for a new iteration to start before the end of previous one if data dependency allows it
        backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]] = self.backedges
        for mb in mf:
            mb: MachineBasicBlock
            orderingInputs = []
            for pred in mb.predecessors():
                pred: MachineBasicBlock
                if (pred, mb) not in backedges:
                    o = self.blockMeta[pred].orderingOut
                    if o is not None:
                        orderingInputs.append(o)

            mbSync: MachineBasicBlockMeta = self.blockMeta[mb]
            if not orderingInputs:
                # must remove ordering because this is a first ordered operation and it does not have any ordering dependence
                for i in mbSync.orderingIn.dependent_inputs:
                    unlink_hls_node_input_if_exists(i)
                    i.obj._removeInput(i.in_i)

                if mbSync.orderingIn is mbSync.orderingOut:
                    mbSync.orderingOut = None
                mbSync.orderingIn = None
            else:
                for last, i in iter_with_last(orderingInputs):
                    if last:
                        if mbSync.orderingIn is mbSync.orderingOut:
                            mbSync.orderingOut = i
                        HlsNetNodeOutLazy_replace(mbSync.orderingIn, i)
                    else:
                        for depI in mbSync.orderingIn.dependent_inputs:
                            depI: HlsNetNodeIn
                            # create a new input for ordering connection
                            depI2 = depI.obj._addInput("orderingIn")
                            HlsNetNodeOut_connectHlsIn_crossingHierarchy(i, depI2, "ordering")

    @override
    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        raise NotImplementedError("This class does not have run() method because it is "
                                  "a special case customized for each build in Platform class. "
                                  "Use object netlist translation methods directly.")
