from typing import Set, Tuple, List, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock, \
    MachineLoop, Register, MachineRegisterInfo
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    LoopChanelGroup, LOOP_CHANEL_GROUP_ROLE, HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.ports import link_hls_nodes, HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.ssa.translation.llvmMirToNetlist.blockEn import resolveBlockEn
from hwtHls.ssa.translation.llvmMirToNetlist.branchOutLabel import BranchOutLabel
from hwtHls.ssa.translation.llvmMirToNetlist.datapath import HlsNetlistAnalysisPassMirToNetlistDatapath, \
    BlockLiveInMuxSyncDict
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta, ADD_ORDERING_PREPEND
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import MachineEdgeMeta, MACHINE_EDGE_TYPE
from hwtHls.ssa.translation.llvmMirToNetlist.resetValueExtract import ResetValueExtractor
from hwtHls.ssa.translation.llvmMirToNetlist.utils import _createSyncForAnyInputSelector, \
    LoopPortGroup
from hwtHls.ssa.translation.llvmMirToNetlist.valueCache import MirToHwtHlsNetlistValueCache
from hwtHls.typingFuture import override


class HlsNetlistAnalysisPassMirToNetlist(HlsNetlistAnalysisPassMirToNetlistDatapath):
    """
    This object translates LLVM MIR to hwtHls HlsNetlist (this class specifically contains control related things)

    When converting from MIR we are using:
    * Forward analysis of block synchronization type to avoid complexities on synchronization type change.
    * Each ordering between IO is strictly specified (can be specified to none). This is used to generate channel synchronization
      flags and to improve thread level parallelism.
    * MIR object may override its translation. This is used to implemented various plugins with minimum effort.
      For example the read from some interface may lower itself to multiple nodes which will implement bus protocol.
    * Loops and backedges are handled explicitly. The loop recognizes "break", "continue", "predecessor" branches and has internal state
      which describes if the loop is busy or not. This state is used to control individual channels.

    Errors in synchronization are usually caused faulty user input. For example if the user code can contain obvious deadlock.
    But the main problem is that for an user it is nearly impossible to debug this if tool implements
    the synchronization for the circuit (which is the case). From this reason a translation from MIR to netlist must be done
    1 to 1 as much as possible. The goal is to be able to find ordering and buffer depletion errors from MIR and from the timeline
    and to have a method to specify the ordering for any node.


    The problem of channel synchronization when translating from MIR:
    * The MIR is assembler like format, control flow is specified as a position in code and data is globally visible.
      Reads and writes do happen one by one.
    * In netlist the control flow is represented as a enable flag, any instruction can run in parallel if restrictions allow it.
    * The :class:`hwtLib.handshaked.streamNode.StreamNode` uses extraCond,skipWhen notation to build arbitrary
      IO synchronization, but the problem is that we have to avoid combinational loops and deadlocks.
    * Resolving of this condition is hard to debug because the thing does not have any linear code flow.
       * From this reason we need to

    Consider this example:
    * Code simply adds incoming values from "channels" if there is an incoming data from every channel,
      and continuously writing sum to output "out".

    .. code-block:: Python

        x = 0
        # a channel with a control flag from predecessor of the loop which will be read only if loop is not running
        # to execute the loop
        while True:
            # value of 'x' is passed from end of the loop to loop header using backedge buffer,
            # which is a hidden IO of the loop body and header
            # We also need a flag which describes the predecessor of this block, for this we need:
            #  * a backedge buffer from the end of loop body will be read only if the loop is running
            if all(ch.hasData() for ch in channels):
                for ch in channels:
                    x += ch.read()
            out.write(x)

    * It is easy to see that if everything is scheduled to 1 clock cycle all input channels have to provide the data
      and out must be ready to accept the data (the hidden channels for "x" and control will be always ready).

    * However consider this modification:

    .. code-block:: Python

        x = 0
        while True:
            if all(ch.hasData() for ch in channels):
                for ch in channels:
                    if x == 10:
                       delay(2*clkPeriod)
                    x += ch.read()

            out.write(x)

    * With code branches where which do not have a constant duration there is this problem:
      There are multiple times when "ch" can be read which is likely to result in modification of order in which "channels" are read.
      This may result in deadlock (e.g. one of the "channels" is "out" and second of "channels" is "out" 1 clk delayed).
    """

    def extractRstValues(self, mf: MachineFunction, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        with self.dbgTracer.scoped(ResetValueExtractor, None):
            return ResetValueExtractor(
                self.builder, self.valCache, self.liveness,
                self.blockSync, self.edgeMeta, self.regToIo,
                self.dbgTracer
            ).apply(mf, threads)

    def _getControlFromPred(self, pred: MachineBasicBlock, mb: MachineBasicBlock, mbSync: MachineBasicBlockMeta, eMeta: MachineEdgeMeta):
        edge = (pred, mb)
        # insert explicit sync on control input
        dataAsControl = eMeta.reuseDataAsControl
        # print("mb pred", mb.getNumber(), pred.getNumber(), control, dataAsControl)
        if dataAsControl is None:
            controlO = self.valCache.get(pred, BranchOutLabel(mb), BIT)
            if mbSync.needsControl:
                control = eMeta.getBufferForReg(edge).obj
            else:
                control = None
        else:
            assert mbSync.needsControl
            control = eMeta.getBufferForReg(dataAsControl)
            controlO = self.builder.buildReadSync(control)
            control = control.obj

        return dataAsControl, control, controlO

    def _collectLiveInDataChannels(self, pred: MachineBasicBlock,
                                   mb: MachineBasicBlock,
                                   blockLiveInMuxInputSync: BlockLiveInMuxSyncDict,
                                   dataAsControl: Optional[Register],
                                   MRI: MachineRegisterInfo):
        allInputDataChannels: List[HlsNetNodeExplicitSync] = []
        # for non backedge edges the sync is not required as the data is received from previous stage in pipeline or state in FSM
        for liveIn in self.liveness[pred][mb]:
            liveIn: Register
            if not self._regIsValidLiveIn(MRI, liveIn) or (dataAsControl is not None and liveIn == dataAsControl):
                continue

            liveInSync: HlsNetNodeExplicitSync = blockLiveInMuxInputSync[(pred, mb, liveIn)]
            allInputDataChannels.append(liveInSync)
        return allInputDataChannels

    def _handleArbitrationLogicOnLoopInput(self, loopStatus: HlsNetNodeLoopStatus,
                                           pred: MachineBasicBlock,
                                           mb: MachineBasicBlock,
                                           eMeta: MachineEdgeMeta,
                                           control: HlsNetNodeReadOrWriteToAnyChannel,
                                           controlO: HlsNetNodeOut,
                                           loopBusy: HlsNetNodeOut, loopBusy_n: HlsNetNodeOut,
                                           allInputDataChannels: List[HlsNetNodeExplicitSync],
                                           dataAsControl: Optional[Register],
                                           loopExecs: LoopPortGroup,
                                           loopReenters: LoopPortGroup):
        # predMbSync: MachineBasicBlockMeta = self.blockSync[pred]
        if any(l.headerBlockNum == mb.getNumber() for l in eMeta.reenteringLoops):
            # reenter
            if eMeta.reenteringLoops[0].headerBlockNum == mb.getNumber():
                lcg = eMeta.getLoopChannelGroup()
                if not lcg.members:
                    lcg.appendWrite(control.associatedWrite, True)
                else:
                    assert lcg.members and lcg.getChannelWhichIsUsedToImplementControl() is control.associatedWrite, (eMeta, lcg.members)
                # control.setNonBlocking()
                cp, cpO = loopStatus.addReenterPort(pred.getNumber(), mb.getNumber(), lcg)
            else:
                raise NotImplementedError("ask owner of channel for allocation")

            assert isinstance(cp, HlsNetNodeRead), cp
            loopReenters.append((cpO, cp, allInputDataChannels))
            cp.addControlSerialExtraCond(loopBusy)
            cp.addControlSerialSkipWhen(loopBusy_n)

            # if isinstance(cp.associatedWrite, HlsNetNodeLoopExitWrite):
            #    # add because it was just generated
            #    predMbSync.addOrderedNode(cp.associatedWrite, atEnd=True)
        else:
            # enter
            assert any(l.headerBlockNum == mb.getNumber() for l in eMeta.enteringLoops)
            if eMeta.enteringLoops[0].headerBlockNum == mb.getNumber():
                lcg = eMeta.getLoopChannelGroup()
                if not lcg.members:
                    lcg.appendWrite(control.associatedWrite, True)
                else:
                    assert lcg.members and lcg.getChannelWhichIsUsedToImplementControl() is control.associatedWrite, (eMeta, lcg.members)
                # control.setNonBlocking()
                cp, cpO = loopStatus.addEnterPort(pred.getNumber(), mb.getNumber(), lcg)
            else:
                raise NotImplementedError("ask owner of channel for allocation")

            assert isinstance(cp, HlsNetNodeRead), cp
            loopExecs.append((cpO, cp, allInputDataChannels))
            cp.addControlSerialExtraCond(loopBusy_n)
            cp.addControlSerialSkipWhen(loopBusy)
            w = cp.associatedWrite
            if dataAsControl is None:
                # if this is already existing channel (data channel) we do not have to re-add conditions
                w.addControlSerialExtraCond(controlO)
                w.addControlSerialSkipWhen(self.builder.buildNot(controlO))
            # else:
            #    assert isinstance(controlO, HlsNetNodeOutLazy), controlO
            #    valCache.add(pred, BranchOutLabel(mb), control.getValidNB())
            #    add BranchOutLabel(mb)= control.extraCond & ~control.skipWhen

            # if isinstance(w, HlsNetNodeLoopExitWrite):
            #    # :note: if this was just newly generated we must have add ordering
            #    predMbSync.addOrderedNode(w, atEnd=True)
        return cpO

    def _resolveLoopIoSync(self, mb: MachineBasicBlock,
                           mbSync: MachineBasicBlockMeta,
                           loopStatus: HlsNetNodeLoopStatus,
                           loop: MachineLoop,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        assert mbSync.needsControl and mbSync.isLoopHeader, ("This should be called only for loop headers with physical loop, bb", mb.getNumber())
        assert mbSync.loopStatusNode is loopStatus, (mb.getNumber(), mbSync.loopStatusNode, loopStatus)
        valCache: MirToHwtHlsNetlistValueCache = self.valCache
        builder = self.builder
        loopReenters: LoopPortGroup = []
        loopExecs: LoopPortGroup = []
        loopBusy = loopStatus.getBusyOutPort()
        loopBusy_n = builder.buildNot(loopBusy)
        MRI = self.mf.getRegInfo()

        for pred in mb.predecessors():
            pred: MachineBasicBlock
            edge = (pred, mb)
            eMeta: MachineEdgeMeta = self.edgeMeta[edge]

            if eMeta.etype == MACHINE_EDGE_TYPE.RESET:
                # :note: rstPredeccessor will is inlined
                continue
            elif eMeta.etype == MACHINE_EDGE_TYPE.DISCARDED:
                # :note: discarded edges do have no control effect
                continue
            dataAsControl, control, controlO = self._getControlFromPred(pred, mb, mbSync, eMeta)
            allInputDataChannels = self._collectLiveInDataChannels(pred, mb, blockLiveInMuxInputSync, dataAsControl, MRI)
            cpO = self._handleArbitrationLogicOnLoopInput(loopStatus, pred, mb, eMeta, control, controlO, loopBusy, loopBusy_n,
                                                          allInputDataChannels, dataAsControl, loopExecs, loopReenters)
            valCache.add(mb, pred, cpO, False)
            # loopStatus.addEnterPort(pred.getNumber(), mb.getNumber(), eMeta.getLoopChannelGroup())

        # loopBusy select if loop should process inputs from loopReenters or from loopExecs
        # if busy skip channels for entry of the loop
        # if not busy skip channels for reenter of the loop
        _createSyncForAnyInputSelector(builder, loopReenters, loopBusy, loopBusy_n)
        _createSyncForAnyInputSelector(builder, loopExecs, loopBusy_n, loopBusy)

        # for each exit skip wait on data if the loop was not executed
        if not loop.hasNoExitBlocks():
            # loop has exits
            self._resolveLoopIoSyncForExit(loopStatus, loop, loopExecs, mb)

    # def _resolveLoopIoSyncAddLatencyToExitReads(self, loopStatus: HlsNetNodeLoopStatus, edgeMeta: MachineEdgeMeta):
    #    """
    #    Postpone read of exit ports by 1 clock cycle from clock cycle where execution of the loops starts (where loopStatus is)
    #    to prevent combinational loop from executing and exiting loop in zero time and to prevent deadlock if loop body takes at least one
    #    clock cycle.
    #    """
    #    exitChWrites = edgeMeta.getLoopChannelGroup().members
    #    if exitChWrites:
    #        for enterGroup in loopStatus.fromEnter:
    #            enterGroup: LoopChanelGroup
    #            enterWrite = enterGroup.getChannelWhichIsUsedToImplementControl()
    #
    #            delay = HlsNetNodeDelayClkTick(self.netlist, 1, HVoidOrdering, "loopExitDelay")
    #            self.netlist.nodes.append(delay)
    #            link_hls_nodes(enterWrite.getOrderingOutPort(), delay._inputs[0])
    #            for exitChWrite in exitChWrites:
    #                link_hls_nodes(delay._outputs[0], exitChWrite._addInput("orderingIn"))
    #
    def _resolveLoopIoSyncForExit(self, loopStatus: HlsNetNodeLoopStatus, loop: MachineLoop, loopExecs: LoopPortGroup, mb: MachineBasicBlock):
        builder = loopStatus.netlist.builder
        valCache: MirToHwtHlsNetlistValueCache = self.valCache

        if loopExecs:
            anyEnterExecuted_n = NOT_SPECIFIED
            for _, exeRead, _  in loopExecs:
                w = exeRead.associatedWrite
                if w.skipWhen is None:
                    anyEnterExecuted_n = 0
                    break
                else:
                    dep = w.dependsOn[w.skipWhen.in_i]
                    if anyEnterExecuted_n is NOT_SPECIFIED:
                        anyEnterExecuted_n = dep
                    else:
                        anyEnterExecuted_n = builder.buildAnd(anyEnterExecuted_n, dep)
        else:
            anyEnterExecuted_n = 0

        # for every exit build a channel which notifies the loop status
        for edge in loop.getExitEdges():
            (exitBlock, exitSucBlock) = edge

            isExitFromParentLoop = False
            p: MachineLoop = loop.getParentLoop()
            while p is not None:
                if p.getHeader() == exitSucBlock or not p.containsBlock(exitSucBlock):
                    if self.blockSync[p.getHeader()].isLoopHeaderOfFreeRunning:
                        # parent loop was just found out to be without HW representation
                        break
                    isExitFromParentLoop = True
                    break
                p = p.getParentLoop()

            edgeMeta: MachineEdgeMeta = self.edgeMeta[edge]
            # self._resolveLoopIoSyncAddLatencyToExitReads(loopStatus, edgeMeta)

            eMbSync: MachineBasicBlockMeta = self.blockSync[exitBlock]
            # if exiting loop return token to HlsNetNodeLoopStatus

            if (isExitFromParentLoop or edgeMeta.etype in (MACHINE_EDGE_TYPE.DISCARDED, MACHINE_EDGE_TYPE.NORMAL)):
                # if it is exit from parent loop  we let parent loop add flags to write node
                eRead = None
                eWrite = None
            else:
                edgeDescriptor = edgeMeta.reuseDataAsControl  if edgeMeta.reuseDataAsControl is not None else edge
                eRead = edgeMeta.getBufferForReg(edgeDescriptor)
                eRead: HlsNetNodeReadAnyChannel = eRead.obj
                # make read from exit channel the first read in successor block
                self.blockSync[exitSucBlock].addOrderedNode(eRead, ADD_ORDERING_PREPEND)
                eWrite = eRead.associatedWrite
                assert isinstance(eWrite, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)), eWrite

            # register and optionally construct EXIT_NOTIFY_TO_HEADER port
            controlOrig = valCache.get(exitBlock, BranchOutLabel(exitSucBlock), BIT)
            if exitSucBlock == mb and eWrite is not None:
                exitForHeaderW = eWrite
                raise NotImplementedError()
            else:
                exitForHeaderR = self._constructBackedgeBuffer(
                    f"bb{exitBlock.getNumber():d}_to_bb{exitSucBlock.getNumber():d}_loopExit",
                    exitBlock, mb,
                    None, builder.buildConstPy(HVoidOrdering, None), True)
                # [todo] add exits also for parent loops
                # edgeMeta.buffersForLoopExit.append(exitForHeaderR) # :note: buffersForLoopExit is not for EXIT_NOTIFY_TO_HEADER
                exitForHeaderR.obj.setNonBlocking()
                exitForHeaderW: HlsNetNodeWriteBackedge = exitForHeaderR.obj.associatedWrite
                # this channel will asynchronously notify loop header, it is not required
                # to have ready sync signal
                exitForHeaderW._isBlocking = False
                exitForHeaderW.allocationType = BACKEDGE_ALLOCATION_TYPE.IMMEDIATE
                exitForHeaderW._rtlUseReady = exitForHeaderR.obj._rtlUseReady = False
                # exitForHeaderW._rtlUseValid = exitForHeaderR.obj._rtlUseValid = False

                self._addExtraCond(exitForHeaderW, controlOrig, eMbSync.blockEn)
                # skipWhen is required because we do not want this to stall parent stage
                self._addSkipWhen_n(exitForHeaderW, controlOrig, eMbSync.blockEn)
                # w.channelInitValues = ((0,),)
                lcg = LoopChanelGroup([(exitBlock.getNumber(),
                                        exitSucBlock.getNumber(),
                                        LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER)])
                lcg.appendWrite(exitForHeaderW, True)

            loopStatus.addExitToHeaderNotifyPort(exitBlock.getNumber(), exitSucBlock.getNumber(), lcg)

            if eWrite is not None:
                # make write to exit channel the last last in block from which there is jump outside of loop
                # :note: ordering should be already added
                # eMbSync.addOrderedNode(eWrite, True)
                self._addExtraCond(eWrite, controlOrig, eMbSync.blockEn)
                self._addSkipWhen_n(eWrite, controlOrig, eMbSync.blockEn)

                # avoid read of data/control on exits if the loop was not entered
                # [todo] same for data channels on this edge
                # :note: exit edge may be reenter to parent loop, or enter to other loop
                if edgeMeta.etype == MACHINE_EDGE_TYPE.BACKWARD:
                    # if exit is backedge the read from exit happens before any enter is written
                    # because of this we must use backedge for anyEnterExecuted_n flag and initialize it to 0
                    anyEnterExecuted_n = self._constructBackedgeBuffer(f"bb{mb.getNumber()}_wasEntered",
                                                                       exitBlock, exitSucBlock,
                                                                       None, anyEnterExecuted_n, True)
                    w: HlsNetNodeWriteBackedge = anyEnterExecuted_n.obj.associatedWrite
                    w.channelInitValues = ((0,),)
                else:
                    assert isinstance(eRead, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge))

                # e.addControlSerialExtraCond(anyEnterExecuted)
                # if anyEnterExecuted_n != 0:
                #    eRead.addControlSerialSkipWhen(anyEnterExecuted_n)

                # update cache so successor uses the port from loop control exit port
                # controlAfterExit = eSuc.getValid()
                # valCache.add(exitBloc, BranchOutLabel(exitSucBlock), controlAfterExit, True)
                # valCache.add(exitSucBlock, exitBloc, controlAfterExit, False)

                # register exit write for the loop
                lcg = eWrite._loopChannelGroup
                if lcg is None:
                    lcg = LoopChanelGroup([(exitBlock.getNumber(),
                                            exitSucBlock.getNumber(),
                                            LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)])
                    lcg.appendWrite(eWrite, True)

                lcg.associateWithLoop(loopStatus, LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR)

    def resolveLoopControl(self,
                           mf: MachineFunction,
                           blockLiveInMuxInputSync: BlockLiveInMuxSyncDict):
        """
        Construct the loop control logic at the header of the loop.
        """
        netlist: HlsNetlistCtx = self.netlist
        for mb in mf:
            mb: MachineBasicBlock
            mbSync: MachineBasicBlockMeta = self.blockSync[mb]

            if mbSync.needsControl and mbSync.isLoopHeader and not mbSync.isLoopHeaderOfFreeRunning:
                loop = self.loops.getLoopFor(mb)
                assert loop is not None
                assert mbSync.loopStatusNode is None, mbSync
                mbSync.loopStatusNode = loopStatus = HlsNetNodeLoopStatus(netlist, f"loop_bb{mb.getNumber():d}")
                self.nodes.append(loopStatus)
                self._resolveLoopIoSync(mb, mbSync, loopStatus, loop, blockLiveInMuxInputSync)

    def resolveBlockEn(self, mf: MachineFunction,
                       threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
        """
        Resolve control flow enable for instructions in the block.
        """
        return resolveBlockEn(self, mf, threads, self.translatedBranchConditions)

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
                    o = self.blockSync[pred].orderingOut
                    if o is not None:
                        orderingInputs.append(o)

            mbSync: MachineBasicBlockMeta = self.blockSync[mb]
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
                        if mbSync.orderingIn is mbSync.orderingOut:
                            mbSync.orderingOut = i
                        mbSync.orderingIn.replaceDriverObj(i)
                    else:
                        for depI in mbSync.orderingIn.dependent_inputs:
                            depI: HlsNetNodeIn
                            # create a new input for ordering connection
                            depI2 = depI.obj._addInput("orderingIn")
                            link_hls_nodes(i, depI2)

    @override
    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        raise NotImplementedError("This class does not have run() method because it is "
                                  "a special case customized for each build in Platform class. "
                                  "Use object netlist translation methods directly.")
