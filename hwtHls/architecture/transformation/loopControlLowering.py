from typing import Union, Dict, Tuple

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.defs import BIT
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsAndRtlNetlistPass import HlsAndRtlNetlistPass
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.architecture.transformation.utils.syncUtils import createBackedgeInClkWindow
from hwtHls.netlist.builder import _replaceOutPortWith
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet
from hwtHls.architecture.transformation.simplify import ArchElementValuePropagation
from hwtHls.architecture.transformation.dce import ArchElementDCE


class HlsAndRtlNetlistPassLoopControlLowering(HlsAndRtlNetlistPass):
    """
    Rewrite :class:`HlsNetNodeLoopStatus` (kind of lock guarding inputs to loop) using channel communication.
    """

    @classmethod
    def _lowerHlsNetNodeLoopStatus(cls, dbgTracer: DebugTracer,
                                   parent: ArchElement,
                                   loopStatus: HlsNetNodeLoopStatus,
                                   worklist: SetList[HlsNetNode]):
        """
        Replace :class:`HlsNetNodeLoopStatus` with new channel which will store lock token if necessary.
        
        :param loopStatus: node to lower
        :param worklist: worklist for DCE and simplify/CSE
        """
        if loopStatus.scheduledZero is None:
            raise NotImplementedError("This pass is expected to be applied only on scheduled loops", loopStatus)

        name = loopStatus.name
        if not name:
            name = f"loop{loopStatus._id:d}"

        if loopStatus.fromEnter:
            lastFromEnter = loopStatus.fromEnter[-1].getChannelUsedAsControl()
            assert lastFromEnter.associatedRead._isBlocking, (
                "last channel from enter must not be non-blocking so this does not execute if any enter is not valid"
                " (it would prematurely consume loop lock token, among other things)",
                loopStatus, lastFromEnter.associatedRead)
        assert loopStatus.fromReenter, ("There must be reenter if this is a loop", loopStatus)
        lastFromReenter = loopStatus.fromReenter[-1].getChannelUsedAsControl()
        assert lastFromReenter.associatedRead._isBlocking, (
            "last channel from reenter must not be non-blocking so this does not execute if any reenter is not valid",
            loopStatus, lastFromReenter.associatedRead)
        builder = parent.builder
        netlist = loopStatus.netlist
        clkPeriod = netlist.normalizedClkPeriod
        scheduledZero = loopStatus.scheduledZero
        clkIndex = indexOfClkPeriod(scheduledZero, clkPeriod)
        syncNode = (parent, clkIndex)
        isAlwaysBusy = loopStatus._isEnteredOnExit and not loopStatus.fromEnter
        if isAlwaysBusy:
            # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
            busyReg_n_Out = None  # c1._outputs[0]

            # replace busy negations with 0
            _busyReg_n_Out = None
            for u in tuple(loopStatus.usedBy[loopStatus.getBusyOutPort().out_i]):
                if isinstance(u.obj, HlsNetNodeOperator) and u.obj.operator == HwtOps.NOT:
                    if _busyReg_n_Out is None:
                        _busyReg_n_Out = builder.buildScheduledConstPy(parent, clkIndex, BIT, 0)
                    replaceOperatorNodeWith(u.obj, _busyReg_n_Out, worklist)
            # replace busy with 1
            _replaceOutPortWith(loopStatus.getBusyOutPort(), builder.buildScheduledConstPy(parent, clkIndex, BIT, 1), worklist)

        else:
            # prepare backedge to store busyReg
            if loopStatus.fromEnter:
                channelInitValue = ()  # loop lock unlocked (loop is not busy after reset)
            else:
                channelInitValue = NOT_SPECIFIED  # loop lock locked (loop is busy after reset)
            # busyReg_n will be 1 if loop is idle and during first iteration
            busyReg_n_R, busyReg_n_W = createBackedgeInClkWindow(parent, clkIndex, f"{name:s}_busy_n", HVoidData, channelInitValue)
            busyReg_n_Out = busyReg_n_R.getValidNB()
            busyReg_Out = builder.buildNot(busyReg_n_Out)
            scheduleUnscheduledControlLogic(syncNode, busyReg_Out)
            _replaceOutPortWith(loopStatus.getBusyOutPort(), busyReg_Out, worklist)
            # replace busy negations with busyReg_n_Out
            for u in tuple(busyReg_Out.obj.usedBy[busyReg_Out.out_i]):
                if isinstance(u.obj, HlsNetNodeOperator) and u.obj.operator == HwtOps.NOT:
                    replaceOperatorNodeWith(u.obj, busyReg_n_Out, worklist)

        groupToEdgeAndPort: Dict[LoopChanelGroup, Tuple[Tuple[int, int], Union[HlsNetNodeOut, HlsNetNodeIn]]] = {
            lcg: (edge, port) for edge, (lcg, port) in loopStatus._bbNumberToPorts.items()}

        # has the priority and does not require sync token (because it already owns it)
        assert loopStatus.fromReenter, (loopStatus, "Must have some reenters otherwise this is not the loop")

        # builder.operatorCache.clear()

        newExit = NOT_SPECIFIED
        if loopStatus.fromExitToHeaderNotify:
            # returns the control token
            _newExit = []
            for channelGroup in loopStatus.fromExitToHeaderNotify:
                channelGroup: LoopChanelGroup
                edge, port = groupToEdgeAndPort[channelGroup]
                # port of loopStatus should be connected to a validNB of exit channel read
                d = loopStatus.dependsOn[port.in_i]
                port.disconnectFromHlsOut(d)  # unlink from loopStatus because we will remove it later
                _newExit.append(d)

            newExit = builder.buildOrVariadic(_newExit, f"{name:s}_newExit")

        # newEnter = NOT_SPECIFIED
        # if loopStatus.fromEnter:
        #    # takes the control token
        #    en = builder.buildNot(busyReg_n_Out)  # :note: the statusBusyReg is 0 in the first clock of the loop execution
        #    _newEnter = []
        #    for channelGroup in loopStatus.fromEnter:
        #        channelGroup: LoopChanelGroup
        #        channelRead = channelGroup.getChannelUsedAsControl().associatedRead
        #        _newEnter.append(channelRead.getValidNB())
        #
        #    newEnter = builder.buildAnd(en, builder.buildOrVariadic(_newEnter, f"{name:s}_newEnter"))  # en & Or(*_newEnter)

        if not isAlwaysBusy or not loopStatus.fromExitToHeaderNotify:
            # deactivate write so lock is never released
            busyReg_n_W.addControlSerialExtraCond(builder.buildScheduledConstPy(parent, clkIndex, BIT, 0), addDefaultScheduling=True)
            busyReg_n_W.addControlSerialSkipWhen(builder.buildScheduledConstPy(parent, clkIndex, BIT, 1), addDefaultScheduling=True)

        if loopStatus.fromExitToHeaderNotify:
            assert newExit is not NOT_SPECIFIED, (newExit, loopStatus)
            # return lock token on loop exit
            scheduleUnscheduledControlLogic(syncNode, newExit)
            newExit.connectHlsIn(busyReg_n_W.getForceEnPort(), checkCycleFree=False)

        netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, loopStatus, worklist)
        # # new exe or reenter should be executed only if stage with this node has ack
        # # exit should be executed only if stage with exit write has ack
        # if isAlwaysBusy:
        #    # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
        #    assert busyReg_n_Out is None
        #
        # elif not loopStatus.fromExitToHeaderNotify:  # not loopStatus.fromEnter and
        #    # this is infinite loop without predecessor, it will run infinitely but in just one instance
        #    # raise AssertionError("This node should be optimized out if state of the loop can't change", loopStatus)
        #
        #    #assert busyReg_n_Out is None
        #    # assert newEnter is NOT_SPECIFIED, (newEnter, loopStatus)
        #    assert newExit is NOT_SPECIFIED, (newExit, loopStatus)
        #
        # # elif loopStatus.fromEnter and not loopStatus.fromExitToHeaderNotify:
        # #    # this is an infinite loop which has a predecessor, once started it will be closed for new starts
        # #    # :attention: we pick the data from any time because this is kind of back edge
        # #    assert newEnter, (newEnter, loopStatus)
        # #    assert newExit is NOT_SPECIFIED, (newExit, loopStatus)
        # #    # if newEnter:
        # #    #     loopLock = 0
        # #    busyNext = builder.buildOr(busyReg_n_Out, newEnter)
        # #    scheduleUnscheduledControlLogic(syncNode, busyNext)
        # #    busyNext.connectHlsIn(busyReg_n_In, checkCycleFree=False)
        #
        # elif loopStatus.fromExitToHeaderNotify:  # loopStatus.fromEnter and
        #    # loop with a predecessor and successor
        #    # assert newEnter is not NOT_SPECIFIED, (newEnter, loopStatus)
        #    assert newExit is not NOT_SPECIFIED, (newExit, loopStatus)
        #    scheduleUnscheduledControlLogic(syncNode, newExit)
        #    newExit.connectHlsIn(busyReg_n_W.getForceEnPort(), checkCycleFree=False)
        #    # becomesBusy = builder.buildAnd(newEnter, builder.buildNot(newExit))  # newEnter & ~newExit
        #    # becomesFree = builder.buildAnd(builder.buildNot(newEnter), newExit)  # ~newEnter & newExit
        #    # if becomesBusy:
        #    #    statusBusyReg = 1
        #    # elif becomesFree:
        #    #    statusBusyReg = 0
        #    # busyNext = builder.buildAnd(
        #    #    builder.buildOr(becomesBusy, busyReg_n_Out),
        #    #    builder.buildNot(becomesFree))
        #    # scheduleUnscheduledControlLogic(syncNode, busyNext)
        #    # busyNext.connectHlsIn(
        #    #    busyReg_n_In, checkCycleFree=False)
        #    # # allow for update of busy on exit if this node does not have ack at the moment
        #    # becomesFree.connectHlsIn(busyReg_n_W.getForceEnPort(), checkCycleFree=False)
        #
        # # elif not loopStatus.fromEnter and loopStatus.fromExitToHeaderNotify:
        # #    # loop with no predecessor and successor
        # #    #
        # #    assert newEnter is NOT_SPECIFIED, (newEnter, loopStatus)
        # #    assert newExit is not NOT_SPECIFIED, (newExit, loopStatus)
        # #    newExit_n = builder.buildNot(newExit)
        # #    scheduleUnscheduledControlLogic(syncNode, newExit_n)
        # #    # if not exit busy = 1
        # #    newExit_n.connectHlsIn(busyReg_n_In)
        # #    busyReg_n_W.addControlSerialExtraCond(newExit_n, addDefaultScheduling=True)
        # #    # if newExit:
        # #    #    statusBusyReg = 0 # set even if current data not read, keep it until fist read
        # #    # else:
        # #    #    statusBusyReg = 1
        # #
        # #    # if exit busy = 0
        # #    newExit.connectHlsIn(busyReg_n_W.getForceWritePort(), checkCycleFree=False)
        # #
        # else:
        #    raise AssertionError("All cases should already be covered in this if", loopStatus)

    @classmethod
    def _lowerHlsNetNodeLoopStatusInNodes(cls, dbgTracer: DebugTracer, parent: Union[HlsNetlistCtx, HlsNetNodeAggregate]):
        changed = False
        worklist: SetList[HlsNetNode] = SetList()
        for n in parent.subNodes:
            if isinstance(n, HlsNetNodeAggregate):
                changed |= cls._lowerHlsNetNodeLoopStatusInNodes(dbgTracer, n)

            elif isinstance(n, HlsNetNodeLoopStatus):
                cls._lowerHlsNetNodeLoopStatus(dbgTracer, parent, n, worklist)
                n.markAsRemoved()
                changed = True

        if changed:
            ArchElementValuePropagation(dbgTracer, [parent, ], worklist, None)
            if isinstance(parent, HlsNetlistCtx):
                ArchElementDCE(parent, parent.subNodes, None)
            else:
                ArchElementDCE(parent.netlist, [parent], None)

        changed |= parent.filterNodesUsingRemovedSet(recursive=False)
        return changed

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        dbgTracer = DebugTracer(None)
        if self._lowerHlsNetNodeLoopStatusInNodes(dbgTracer, netlist):
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
